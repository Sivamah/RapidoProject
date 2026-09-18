# -*- coding: utf-8 -*-
"""
DecisionEngine.run_analysis() coverage — the /api/dmfe/analyze endpoint's
core logic (Finding 7 of the reliability audit,
docs/reports/TARGETED_FINDINGS_VERIFICATION.md): before this file, grepping
tests/*.py for `run_analysis` returned zero matches, so this ~190-line
method was exercised only by a manual script (scripts/test_stale_release.py)
that does not itself assert or fail on its own verdict.

Scope deliberately mirrors test_pipeline_accounting.py's invariant style
rather than re-deriving the compatibility scoring formula (already covered
by test_compatibility.py / test_scoring_unified.py): these tests assert on
run_analysis()'s own orchestration contract --  every pending request is
accounted for exactly once, DMFEAnalysisRun/DMFEBatch rows are persisted
correctly, and analysis_run_id is back-filled only onto batches created by
THIS run (a real, previously-fixed regression -- see the code comment at
decision_engine.py's `db.query(DMFEBatch)...update({"analysis_run_id": ...})`
call).

Also covers the Wave-3 de-duplication fix (`_find_existing_live_batch`):
repeated /analyze calls on an unchanged pending queue must not insert
duplicate DMFEBatch rows for the same request-id set (Finding 1 of the same
audit).
"""

from __future__ import annotations

import json

import pytest

from app.dmfe.compatibility import clear_config_cache
from app.dmfe.decision_engine import decision_engine
from app.dmfe.models import DMFEAnalysisRun, DMFEBatch

ANCHOR_LAT, ANCHOR_LNG = 11.0168, 76.9558


@pytest.fixture(autouse=True)
def _fresh_config_cache():
    """The SystemConfig TTL cache is module-level; clear it around each test."""
    clear_config_cache()
    yield
    clear_config_cache()


def _batch_request_ids(batch: DMFEBatch) -> list:
    return json.loads(batch.request_ids_json or "[]")


# ── Empty queue ──────────────────────────────────────────────────────────────

def test_empty_queue_persists_empty_run(db):
    result = decision_engine.run_analysis(db)

    assert result.total_pending == 0
    assert result.batches_created == 0
    assert result.rejected_count == 0

    runs = db.query(DMFEAnalysisRun).all()
    assert len(runs) == 1
    assert runs[0].total_pending == 0
    assert runs[0].id == result.run_id


# ── Solo (unpaired) request → Individual trip batch ─────────────────────────

def test_solo_request_becomes_individual_batch(db, make_request):
    req = make_request(pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
                        drop_lat=11.02, drop_lng=76.97)
    db.commit()

    result = decision_engine.run_analysis(db)

    assert result.total_pending == 1
    assert result.unmatched_request_ids == [req.id]

    batches = db.query(DMFEBatch).all()
    assert len(batches) == 1
    assert batches[0].decision == "Individual"
    assert batches[0].status == "Individual"
    assert _batch_request_ids(batches[0]) == [req.id]
    assert batches[0].analysis_run_id == result.run_id


# ── analysis_run_id back-fill regression ─────────────────────────────────────

def test_analysis_run_id_backfilled_only_for_this_runs_batches(db, make_request, make_batch):
    """
    The dispatch pipeline (driver_selection.py) persists DMFEBatch rows of
    its own and never sets analysis_run_id. A blanket update would
    misattribute those pre-existing rows to whichever analysis run happens
    to execute next -- this pins the fix (id.in_(run_batch_ids), not a
    blanket NULL update).
    """
    unrelated = make_batch(analysis_run_id=None, status="Dispatched")
    db.commit()

    req = make_request(pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
                        drop_lat=11.02, drop_lng=76.97)
    db.commit()

    result = decision_engine.run_analysis(db)

    db.refresh(unrelated)
    assert unrelated.analysis_run_id is None, (
        "run_analysis() must not back-fill analysis_run_id onto batches it "
        "did not itself create in this run"
    )

    new_batch = (
        db.query(DMFEBatch)
        .filter(DMFEBatch.id != unrelated.id)
        .one()
    )
    assert new_batch.analysis_run_id == result.run_id


# ── Full accounting invariant ────────────────────────────────────────────────

def test_every_pending_request_accounted_for_exactly_once(db, make_request):
    """
    Every request run_analysis() looks at must end up in exactly one of:
    a compatible batch, a rejected batch, or unmatched_request_ids -- never
    zero, never more than one (mirrors the pipeline accounting invariant in
    test_pipeline_accounting.py, applied to the /analyze endpoint instead).
    """
    close_pair = [
        make_request(pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
                     drop_lat=11.02, drop_lng=76.97),
        make_request(pickup_lat=ANCHOR_LAT + 0.001, pickup_lng=ANCHOR_LNG,
                     drop_lat=11.021, drop_lng=76.971),
    ]
    far_solo = make_request(pickup_lat=11.30, pickup_lng=76.70,
                             drop_lat=11.35, drop_lng=76.65)
    db.commit()
    all_ids = {r.id for r in close_pair} | {far_solo.id}

    result = decision_engine.run_analysis(db)

    assert result.total_pending == 3

    accounted = set(result.unmatched_request_ids)
    for b in result.compatible_batches:
        accounted.update(b["request_ids"])
    for b in result.rejected_batches:
        accounted.update(b["request_ids"])

    assert accounted == all_ids, (
        f"accounting mismatch: pending={sorted(all_ids)} accounted={sorted(accounted)}"
    )

    # No request may appear in more than one bucket.
    seen = []
    for b in result.compatible_batches:
        seen.extend(b["request_ids"])
    for b in result.rejected_batches:
        seen.extend(b["request_ids"])
    seen.extend(result.unmatched_request_ids)
    assert len(seen) == len(set(seen)), f"a request was counted twice: {seen}"


# ── De-duplication regression (Wave 3 fix) ───────────────────────────────────

def test_repeated_analyze_does_not_duplicate_batches(db, make_request):
    """
    Finding 1: /analyze never advances SimulationRequest.status, so calling
    it twice on an unchanged pending queue used to insert a second, duplicate
    DMFEBatch row for the same request set every time. This pins the fix.
    """
    req = make_request(pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
                        drop_lat=11.02, drop_lng=76.97)
    db.commit()

    first = decision_engine.run_analysis(db)
    count_after_first = db.query(DMFEBatch).count()
    assert count_after_first == 1

    second = decision_engine.run_analysis(db)
    count_after_second = db.query(DMFEBatch).count()

    assert count_after_second == count_after_first, (
        f"repeated /analyze on an unchanged queue duplicated batches: "
        f"{count_after_first} -> {count_after_second}"
    )
    # The unchanged request is still reported as unmatched both times --
    # dedup must reuse the persisted row, not silently drop the request.
    assert second.unmatched_request_ids == [req.id]


def test_repeated_analyze_still_creates_a_batch_for_a_genuinely_new_request(db, make_request):
    """The dedup fix must not suppress batches for requests it hasn't seen
    before -- only exact-match request-id sets are reused."""
    req1 = make_request(pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
                         drop_lat=11.02, drop_lng=76.97)
    db.commit()
    decision_engine.run_analysis(db)
    assert db.query(DMFEBatch).count() == 1

    req2 = make_request(pickup_lat=11.30, pickup_lng=76.70,
                         drop_lat=11.35, drop_lng=76.65)
    db.commit()

    result = decision_engine.run_analysis(db)

    assert db.query(DMFEBatch).count() == 2
    assert set(result.unmatched_request_ids) == {req1.id, req2.id}
