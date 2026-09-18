# -*- coding: utf-8 -*-
"""
A-DMFE adaptive-package coverage — Finding 7 of the reliability audit
(docs/reports/TARGETED_FINDINGS_VERIFICATION.md): grepping tests/*.py for
`compute_extension_factors`, `batch_quality_score`, `compute_confidence`,
`effective_threshold`, `AdaptiveBatchFormation`, `build_adaptive_reasons`
returned zero matches for every one of them.

Where a function's formula is fully documented and deterministic (the
decision.py threshold/BQS/confidence math, xai.py's attribution), these
tests recompute the expected value from the exact same formula/primitives
the source uses and assert an exact (tolerant-of-float-noise) match -- a
real regression pin, not a placeholder. `compute_extension_factors` is
exercised with context=None / learning_state=None, the one configuration
where every sub-factor collapses to a value fully computable by the test
itself (no opaque ContextProfile internals to reproduce).

`AdaptiveBatchFormation.create_feasible_batches` needs a live DB session and
a real ContextProfile, so its test mirrors batch_generator.py's own call
site verbatim (rules/context/weights/threshold/bqs_threshold construction)
rather than inventing a shape of its own, and asserts the one contract that
matters regardless of scoring specifics: final batches are disjoint (no
request appears in two different returned groups).
"""

from __future__ import annotations

import types

import pytest

from app.engine.distance import haversine
from app.dmfe.score_engine import estimated_delay_score
from app.dmfe.adaptive._util import _clamp01
from app.dmfe.adaptive.factors import EXTENSION_KEYS, compute_extension_factors
from app.dmfe.adaptive.decision import (
    BQS_BASE,
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    batch_quality_score,
    bqs_threshold,
    compute_confidence,
    effective_threshold,
)
from app.dmfe.adaptive.xai import (
    build_adaptive_reasons,
    factor_contributions,
    top_contributors,
)
from app.dmfe.scoring import FACTOR_KEYS


def _req(pickup_lat, pickup_lng, drop_lat=0.0, drop_lng=0.0, demand=1, request_type="ride"):
    """Plain stand-in for a SimulationRequest: compute_extension_factors only
    reads attributes, never touches the DB, so a real ORM row isn't needed."""
    return types.SimpleNamespace(
        pickup_lat=pickup_lat, pickup_lng=pickup_lng,
        drop_lat=drop_lat, drop_lng=drop_lng,
        demand=demand, request_type=request_type,
    )


# ── decision.py: effective_threshold ────────────────────────────────────────

def test_effective_threshold_none_context_returns_base_unchanged():
    assert effective_threshold(70.0, None) == 70.0


def test_effective_threshold_matches_documented_formula():
    ctx = {"traffic_index": 0.5, "demand_pressure": 0.2, "driver_scarcity": 0.1}
    expected = round(
        max(THRESHOLD_MIN, min(THRESHOLD_MAX, 70.0 + 2.0 * 0.5 - 4.0 * 0.2 + 3.0 * 0.1)), 1
    )
    assert effective_threshold(70.0, ctx) == pytest.approx(expected, abs=1e-9)
    assert effective_threshold(70.0, ctx) == 70.5


def test_effective_threshold_clamped_to_bounds():
    high = effective_threshold(70.0, {"traffic_index": 10.0, "demand_pressure": 0.0, "driver_scarcity": 0.0})
    low = effective_threshold(70.0, {"traffic_index": 0.0, "demand_pressure": 10.0, "driver_scarcity": 0.0})
    assert high == THRESHOLD_MAX
    assert low == THRESHOLD_MIN


# ── decision.py: bqs_threshold ──────────────────────────────────────────────

def test_bqs_threshold_none_context_returns_base():
    assert bqs_threshold(None) == BQS_BASE


def test_bqs_threshold_matches_documented_formula():
    ctx = {"traffic_index": 1.0, "demand_pressure": 0.0, "driver_scarcity": 0.0, "priority_pressure": 0.0}
    expected = round(BQS_BASE + 0.04 * 1.0, 3)
    assert bqs_threshold(ctx) == pytest.approx(expected, abs=1e-9)


def test_bqs_threshold_clamped_to_bounds():
    high = bqs_threshold({"traffic_index": 10.0, "demand_pressure": 0.0, "driver_scarcity": 0.0, "priority_pressure": 0.0})
    low = bqs_threshold({"traffic_index": 0.0, "demand_pressure": 10.0, "driver_scarcity": 0.0, "priority_pressure": 0.0})
    assert high == 0.75
    assert low == 0.40


# ── decision.py: batch_quality_score ────────────────────────────────────────

def test_batch_quality_score_matches_documented_formula():
    compatibility_score = 80.0
    factor_scores = {"route": 0.5}
    extensions = {"vehicle_utilization": 0.6, "environmental": 0.4, "historical_success": 0.5}
    factor_details = {"expected_delay_min": 5.0}
    rules = {"max_allowed_delay_min": 20.0}

    cs_norm = 0.8
    util = 0.6
    savings = 0.5
    delay_ok = 1.0 - 5.0 / 20.0
    env = 0.4
    hist = 0.5
    expected = round(
        0.40 * cs_norm + 0.15 * util + 0.20 * savings + 0.15 * delay_ok
        + 0.05 * env + 0.05 * hist,
        4,
    )

    bqs = batch_quality_score(compatibility_score, factor_scores, extensions, factor_details, rules)
    assert bqs == pytest.approx(expected, abs=1e-9)


def test_batch_quality_score_is_clamped_to_unit_interval():
    # Wildly out-of-range inputs must still land in [0, 1].
    bqs = batch_quality_score(
        1000.0,
        {"route": 5.0},
        {"vehicle_utilization": 5.0, "environmental": 5.0, "historical_success": 5.0},
        {"expected_delay_min": -100.0},
        {"max_allowed_delay_min": 20.0},
    )
    assert 0.0 <= bqs <= 1.0


# ── decision.py: compute_confidence ─────────────────────────────────────────

def test_compute_confidence_matches_documented_formula():
    factor_scores = {"pickup": 0.9, "route": 0.7, "time": 0.6, "capacity": 0.8, "priority": 0.5}
    rules = {"max_allowed_delay_min": 20.0}
    compatibility_score = 78.0
    threshold = 70.0
    delay_min = 4.0

    margin = _clamp01((compatibility_score - threshold) / max(100.0 - threshold, 1.0))
    values = [factor_scores[k] for k in FACTOR_KEYS]
    spread = max(values) - min(values)
    agreement = _clamp01(1.0 - spread)
    delay_ok = _clamp01(1.0 - max(0.0, delay_min) / 20.0)
    expected = round(100.0 * _clamp01(0.55 * margin + 0.25 * agreement + 0.20 * delay_ok), 1)

    conf = compute_confidence(compatibility_score, threshold, factor_scores, delay_min, rules)
    assert conf == pytest.approx(expected, abs=1e-9)


def test_compute_confidence_is_bounded_0_to_100():
    conf = compute_confidence(
        200.0, -50.0, {k: 1.0 for k in FACTOR_KEYS}, -100.0, {"max_allowed_delay_min": 20.0},
    )
    assert 0.0 <= conf <= 100.0


# ── factors.py: compute_extension_factors (context=None, learning_state=None) ──

def test_compute_extension_factors_returns_all_keys_in_unit_range():
    rules = {"max_allowed_delay_min": 20.0, "max_vehicle_capacity": 6, "avg_speed_kmh": 25.0}
    r1 = _req(11.0168, 76.9558)
    r2 = _req(11.03, 76.97)

    scores, details = compute_extension_factors([r1, r2], context=None, rules=rules)

    assert set(scores.keys()) == set(EXTENSION_KEYS)
    for key, val in scores.items():
        assert 0.0 <= val <= 1.0, f"{key} out of [0,1]: {val}"
    for key in (
        "expected_delay_min", "capacity_utilization_pct", "estimated_waiting_min",
        "driver_availability_ratio", "corridor", "historical_success_rate",
        "fleet_efficiency_index", "route_overlap_used",
    ):
        assert key in details


def test_compute_extension_factors_deterministic_values_without_context():
    """
    With context=None and learning_state=None, driver_workload,
    historical_success and environmental collapse to fixed values, and
    expected_delay/vehicle_utilization are fully reproducible from the same
    primitives (haversine / estimated_delay_score) the source itself calls.
    """
    rules = {"max_allowed_delay_min": 20.0, "max_vehicle_capacity": 6, "avg_speed_kmh": 25.0}
    r1 = _req(11.0168, 76.9558, demand=1)
    r2 = _req(11.03, 76.97, demand=1)

    scores, details = compute_extension_factors(
        [r1, r2], context=None, rules=rules, learning_state=None, pair_overlap=0.9,
    )

    # No context -> driver scarcity defaults to 0 -> full headroom.
    assert scores["driver_workload"] == 1.0
    # No learning_state, no context -> neutral historical prior.
    assert scores["historical_success"] == 0.5
    # environmental = clamp(0.6*overlap + 0.4*efficiency); efficiency=0.5 with no fleet context.
    assert scores["environmental"] == pytest.approx(round(0.6 * 0.9 + 0.4 * 0.5, 4), abs=1e-9)
    assert details["route_overlap_used"] == pytest.approx(0.9, abs=1e-9)
    assert details["corridor"] == "ride"

    # expected_delay: same estimated_delay_score() call the source makes for
    # this single pair (n=2 -> exactly one pairwise delay, no averaging effect).
    _, expected_delay_min = estimated_delay_score(
        r1.pickup_lat, r1.pickup_lng, r2.pickup_lat, r2.pickup_lng,
        max_delay_min=20.0, avg_speed_kmh=25.0,
    )
    expected_delay_score = round(1.0 - _clamp01(expected_delay_min / 20.0), 4)
    assert scores["expected_delay"] == pytest.approx(expected_delay_score, abs=1e-3)
    assert details["expected_delay_min"] == pytest.approx(expected_delay_min, abs=1e-6)

    # vehicle_utilization: demand 1+1=2 over max_vehicle_capacity=6.
    solo_util = 1.0 / 6.0
    batch_util = 2.0 / 6.0
    gain = batch_util - solo_util
    expected_util = round(_clamp01(gain / max(0.5, solo_util + 1e-9)), 4)
    assert scores["vehicle_utilization"] == pytest.approx(expected_util, abs=1e-3)


def test_compute_extension_factors_uses_haversine_for_delay():
    """Sanity check the delay factor actually reacts to distance -- two
    pickups 100km apart must score strictly worse than two 100m apart."""
    rules = {"max_allowed_delay_min": 20.0, "max_vehicle_capacity": 6, "avg_speed_kmh": 25.0}
    near1, near2 = _req(11.0168, 76.9558), _req(11.0170, 76.9560)
    far1, far2 = _req(11.0168, 76.9558), _req(12.0, 78.0)

    assert haversine(far1.pickup_lat, far1.pickup_lng, far2.pickup_lat, far2.pickup_lng) > 50

    near_scores, _ = compute_extension_factors([near1, near2], context=None, rules=rules)
    far_scores, _ = compute_extension_factors([far1, far2], context=None, rules=rules)

    assert near_scores["expected_delay"] > far_scores["expected_delay"]


# ── xai.py: factor_contributions / top_contributors ─────────────────────────

def test_factor_contributions_matches_documented_formula():
    weights = {"pickup": 0.30, "route": 0.25, "time": 0.20, "capacity": 0.15, "priority": 0.10}
    factor_scores = {"pickup": 0.8, "route": 0.5, "time": 0.3, "capacity": 0.9, "priority": 0.5}

    contributions = factor_contributions(weights, factor_scores)

    expected = {f: round(w * (factor_scores[f] - 0.5), 4) for f, w in weights.items()}
    assert contributions == pytest.approx(expected, abs=1e-9)


def test_top_contributors_ranks_by_absolute_value_and_drops_near_zero():
    contributions = {"pickup": 0.09, "route": 0.0, "time": -0.04, "capacity": 0.06, "priority": 0.0}

    top = top_contributors(contributions, n=3)

    assert [t["factor"] for t in top] == ["pickup", "capacity", "time"]
    assert all(abs(t["contribution"]) > 1e-4 for t in top)


# ── xai.py: build_adaptive_reasons ──────────────────────────────────────────

def test_build_adaptive_reasons_static_mode_returns_empty():
    reasons = build_adaptive_reasons(
        80.0, 70.0, 0.6, 0.55, 90.0, {}, {}, 5.0, "Compatible", mode="static",
    )
    assert reasons == []


def test_build_adaptive_reasons_compatible_mentions_batched_and_confidence():
    contributions = {"pickup": 0.09, "capacity": 0.06}
    reasons = build_adaptive_reasons(
        80.0, 70.0, 0.6, 0.55, 90.0, contributions, {}, 5.0, "Compatible", mode="adaptive",
    )
    assert any("BATCHED" in r for r in reasons)
    assert any("Decision confidence" in r for r in reasons)


def test_build_adaptive_reasons_incompatible_mentions_rejected_and_delay():
    contributions = {"pickup": -0.09}
    reasons = build_adaptive_reasons(
        60.0, 70.0, 0.3, 0.55, 40.0, contributions, {"historical_success": 0.4}, 8.0,
        "Incompatible", mode="adaptive",
    )
    assert any("REJECTED" in r for r in reasons)
    assert any("Expected delay" in r for r in reasons)


def test_build_adaptive_reasons_individual_is_concise():
    reasons = build_adaptive_reasons(
        0.0, 70.0, 0.0, 0.55, 0.0, {}, {}, 0.0, "Individual", mode="adaptive",
    )
    assert any("INDIVIDUAL" in r for r in reasons)
    assert len(reasons) == 2  # the INDIVIDUAL line + the confidence line


# ── batching.py: AdaptiveBatchFormation ──────────────────────────────────────

def test_adaptive_batch_formation_returns_empty_for_fewer_than_two_pending(db):
    from app.dmfe.adaptive.batching import AdaptiveBatchFormation

    result = AdaptiveBatchFormation().create_feasible_batches(
        pending=[], db=db, mode="adaptive", context=None, weights={},
        rules={}, threshold=70.0, bqs_threshold_value=0.55,
    )
    assert result == []


def test_adaptive_batch_formation_final_batches_are_disjoint(db, make_request):
    """
    Mirrors batch_generator.py's own adaptive call site verbatim (context /
    weights / thresholds construction) so this exercises the real code path,
    not a hand-rolled shape. The one contract asserted -- final batches never
    share a request -- holds regardless of the exact scores produced.
    """
    from app.dmfe.adaptive.batching import AdaptiveBatchFormation
    from app.dmfe.adaptive.context import ContextAwarenessEngine
    from app.dmfe.adaptive.weights import AdaptiveWeightGenerator
    from app.dmfe.adaptive.decision import effective_threshold, bqs_threshold
    from app.dmfe.adaptive.learning import LearningEngine
    from app.dmfe.compatibility import _get_ai_rules, _get_threshold, clear_config_cache

    clear_config_cache()

    anchor_lat, anchor_lng = 11.0168, 76.9558
    pending = [
        make_request(pickup_lat=anchor_lat, pickup_lng=anchor_lng,
                     drop_lat=11.02, drop_lng=76.97),
        make_request(pickup_lat=anchor_lat + 0.001, pickup_lng=anchor_lng,
                     drop_lat=11.021, drop_lng=76.971),
        make_request(pickup_lat=11.30, pickup_lng=76.70,
                     drop_lat=11.35, drop_lng=76.65),
        make_request(pickup_lat=11.301, pickup_lng=76.701,
                     drop_lat=11.351, drop_lng=76.651),
    ]
    db.commit()

    rules = _get_ai_rules(db)
    context = ContextAwarenessEngine().build(db, pending)
    learning_state = LearningEngine.load_state(db)
    weights = AdaptiveWeightGenerator(mode="adaptive").generate(
        db, context, LearningEngine.weight_corrections(db)
    )
    threshold = effective_threshold(_get_threshold(db), context)
    bqs_thr = bqs_threshold(context)

    groups = AdaptiveBatchFormation().create_feasible_batches(
        pending, db, mode="adaptive", context=context, weights=weights,
        rules=rules, threshold=threshold, bqs_threshold_value=bqs_thr,
        learning_state=learning_state,
    )

    seen_ids = set()
    for g in groups:
        ids = {r.id for r in g.requests}
        assert 2 <= len(ids) <= 3, f"unexpected group size: {ids}"
        assert ids.isdisjoint(seen_ids), (
            f"request(s) {ids & seen_ids} appear in more than one final batch"
        )
        seen_ids.update(ids)

    clear_config_cache()
