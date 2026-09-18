"""
ICCES-260 reviewer experiment - R1.5 Acceptance Simulation
==========================================================
A SIMULATION - NOT A HUMAN STUDY.

It models how many requests would be *accepted* (dispatched) under a
post-hoc, compatibility-gated acceptance policy, across deterministic
repeated simulation runs.  DMFE natively dispatches every request - either
into a compatible shared batch or as a fallback solo trip - so a naive
roll-up always yields 100% acceptance.  That 100% is not evidence of
selective acceptance; it is because the engine never turns a request away
once fleet capacity is available.

To answer "what does acceptance look like under a real acceptance gate?",
we apply a POST-HOC COMPATIBILITY-SCORE CUTOFF to the dispatched set:

    accepted(request, cutoff) = dispatched(request) AND
                                best_compatibility_score(request) >= cutoff

* Shared-batch requests carry their batch's compatibility score (0-100).
* Solo/individual trips carry score 0.0 (no compatible pairing was found),
  so they are instantly rejected by any cutoff > 0.
* cutoff = 0 recreates DMFE's unselective behaviour (accept everything that
  a driver can serve) and should read ~100%.
* cutoff = 70 is DMFE's own configured batch-compatibility threshold, so
  that row is the honest head-line: the share of requests that met the
  engine's own quality bar rather than being dispatched solo/fallback.

Explicit assumptions (the model)
--------------------------------
    1. "Dispatched" = request was placed in a dispatched Trip row (shared
       or individual) across the full multi-wave lifecycle.
    2. "Accepted at cutoff c" = dispatched AND its best compatibility score
       >= c.
    3. Score = batch compatibility_score for shared trips, 0.0 for solo
       fallback trips (per the pipeline's individual-trip persistence).
    4. All numbers are SIMULATED outcomes of this assumed acceptance model,
       NOT measured human acceptance.

We NEVER claim these numbers are measured human acceptance.  Statements
are phrased strictly as: "Under the assumed compatibility-gated acceptance
model, simulated acceptance was X%."

Determinism
    Each REPEATS run uses a documented seed and identical workload
    configuration; only the seed (and the wave index) indexes the run.
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(EVAL_DIR.parent))  # backend root

from framework import (  # noqa: E402
    RESULTS_DIR,
    MAX_WAVES,
    SYSTEM_CONFIG,
    ExperimentDB,
    WorkloadRunner,
)

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import SimulationRequest, Trip  # noqa: E402
from app.dmfe.models import DMFEBatch  # noqa: E402

SEED_BASE = 1515
REPEATS = 5
WORKLOAD = 60
# Post-hoc compatibility-score acceptance gate (0 recreates DMFE's
# unselective behaviour; 70 is DMFE's own configured threshold).
CUTOFFS = [0, 30, 50, 60, 70, 75, 80, 85, 90]
DMFE_THRESHOLD = 70.0
PRIORITY_WEIGHTS = {"Low": 0.20, "Medium": 0.60, "High": 1.00}
OUT_FILE = os.path.join(RESULTS_DIR, "r15_acceptance.json")


def _best_scores_by_request(db) -> Dict[int, Dict[str, Any]]:
    """Map request_id -> {"dispatched": bool, "best_compat": float, ...}.

    A request is 'dispatched' if it appears in at least one dispatched Trip
    row (shared or individual) over the whole run.  Its compatibility score
    is the *maximum* across every trip it was placed in, which is the
    most generous reading (a request accepted in any qualifying batch is
    counted at that batch's score).
    """
    scores: Dict[int, Dict[str, Any]] = {}
    for trip in db.query(Trip).all():
        try:
            ids = json.loads(trip.request_ids_json or "[]")
        except (ValueError, TypeError):
            ids = []
        if not ids:
            continue
        score = 0.0
        if trip.is_shared:
            b = trip.batch
            if b is not None and b.compatibility_score is not None:
                score = float(b.compatibility_score)
        for rid in ids:
            entry = scores.setdefault(
                int(rid), {"dispatched": False, "best_compat": 0.0})
            entry["dispatched"] = True
            if score > entry["best_compat"]:
                entry["best_compat"] = score
    return scores


def run_repeat(seed: int) -> Dict[str, Any]:
    exp = ExperimentDB()
    db = SessionLocal()
    try:
        exp.reset_schema()
        config = dict(SYSTEM_CONFIG)
        exp.seed_system_config_with(db, config)
        rng = random.Random(seed)
        exp.seed_fleet(db, rng)

        from app.services.mock_adapters import generate_simulation_requests
        random.seed(seed)
        reqs = generate_simulation_requests(
            count=WORKLOAD, db=db,
            request_types={"ride": 0.40, "food": 0.40, "parcel": 0.20},
        )
        if len(reqs) < WORKLOAD:
            raise RuntimeError(
                f"Run {seed} got {len(reqs)}/{WORKLOAD} requests; aborting "
                f"this repeat (no fabricated rows).")

        runner = WorkloadRunner(WORKLOAD, seed=seed)
        runner.install_probes()
        runner.requests = reqs

        out = runner.run_pipeline(db)
        status_map = {r.id: r.status for r in reqs}
        single = runner.collect_metrics(db, out["trip_ids"], status_map)

        # full-day waves --- the trip lifecycle closes.
        runner.complete_trips_real(db)
        waves = 0
        for _ in range(MAX_WAVES):
            pending = db.query(SimulationRequest).filter(
                SimulationRequest.status == "Pending").count()
            if pending == 0:
                break
            random.seed(seed + 1000 + waves)
            runner._exec_rng = random.Random(seed + 9000 + waves)
            waves += 1
            wout = runner.run_pipeline(db)
            if not wout["trip_ids"]:
                break
            runner.complete_trips_real(db)

        db.expire_all()
        best = _best_scores_by_request(db)

        # base dispatch (unselective engine view): dispatched at all
        dispatched_total = sum(1 for e in best.values() if e["dispatched"])

        def acc_count(cut: float) -> int:
            return sum(
                1 for e in best.values()
                if e["dispatched"] and e["best_compat"] >= cut)

        sweep = {}
        for c in CUTOFFS:
            sweep[str(c)] = {
                "accepted": acc_count(c),
                "accepted_pct": round(acc_count(c) / WORKLOAD * 100.0, 1),
            }

        # per-priority sweep at the DMFE headline threshold
        by_priority: Dict[str, Dict[str, Any]] = {}
        for p in PRIORITY_WEIGHTS:
            by_priority[p] = {"total": 0, "accepted": 0}
        for r in reqs:
            p = r.priority if r.priority in by_priority else "Medium"
            by_priority[p]["total"] += 1
            e = best.get(r.id, {"dispatched": False, "best_compat": 0.0})
            if e["dispatched"] and e["best_compat"] >= DMFE_THRESHOLD:
                by_priority[p]["accepted"] += 1

        # priority-weighted acceptance at the headline threshold
        wsum = 0.0
        for p, d in by_priority.items():
            rate = d["accepted"] / d["total"] if d["total"] else 0.0
            wsum += PRIORITY_WEIGHTS[p] * rate
        weighted = wsum / sum(PRIORITY_WEIGHTS.values())

        return {
            "seed": seed,
            "requests": WORKLOAD,
            "dispatched_total": dispatched_total,
            "dispatched_pct": round(dispatched_total / WORKLOAD * 100.0, 1),
            "compatibility_cutoff_sweep": sweep,
            "headline_at_dmfe_threshold(70)": sweep["70"],
            "per_priority_at_threshold70": {
                p: {
                    "total": d["total"],
                    "accepted": d["accepted"],
                    "accepted_pct": round(
                        d["accepted"] / d["total"] * 100.0, 1) if d["total"] else 0.0,
                } for p, d in by_priority.items()
            },
            "priority_weighted_acceptance_at70_pct": round(weighted * 100.0, 1),
            "single_pass": {
                "batching_rate_pct": single["batching_rate_pct"],
                "shared_trips": single["shared_trips"],
                "individual_trips": single["individual_trips"],
            },
        }
    finally:
        db.close()


def main() -> None:
    runs: Dict[str, Dict[str, Any]] = {}
    for i in range(REPEATS):
        seed = SEED_BASE + i
        runs[str(seed)] = run_repeat(seed)

    # aggregate across repeats, per cutoff
    sweep_agg: Dict[str, Dict[str, float]] = {}
    for c in CUTOFFS:
        vals = [r["compatibility_cutoff_sweep"][str(c)]["accepted_pct"]
                for r in runs.values()]
        sweep_agg[str(c)] = {
            "mean": round(sum(vals) / len(vals), 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
        }

    headline_vals = [
        r["headline_at_dmfe_threshold(70)"]["accepted_pct"] for r in runs.values()]
    weighted_vals = [
        r["priority_weighted_acceptance_at70_pct"] for r in runs.values()]
    dispatched_vals = [r["dispatched_pct"] for r in runs.values()]

    def agg(vals: List[float]) -> Dict[str, float]:
        return {
            "mean": round(sum(vals) / len(vals), 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
        }

    aggregate = {
        "dispatched_pct": agg(dispatched_vals),
        "compatibility_cutoff_sweep": sweep_agg,
        "headline_acceptance_at_threshold70_pct": agg(headline_vals),
        "priority_weighted_acceptance_at70_pct": agg(weighted_vals),
        "repeats": REPEATS,
    }

    result = {
        "experiment": "R1.5 post-hoc acceptance filter "
                      "(compatibility-score cutoff sweep)",
        "reviewer_mapping": "R1.5",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seed_base": SEED_BASE,
        "repeats": REPEATS,
        "workload": WORKLOAD,
        "mode": SYSTEM_CONFIG.get("admfe.mode", "adaptive"),
        "dmfe_compatibility_threshold": DMFE_THRESHOLD,
        "cutoffs": CUTOFFS,
        "assumptions": {
            "human_study": False,
            "model": (
                "accepted(request, cutoff) = dispatched(request) AND "
                "best_compatibility_score(request) >= cutoff.  Shared "
                "requests carry their batch compatibility score (0-100); "
                "solo/fallback trips carry 0.0 (no compatible batch found)."
                "  All numbers are SIMULATED outcomes of this assumed "
                "acceptance model, not measured human acceptance."),
            "score_source": (
                "For each request, the maximum compatibility score across "
                "every dispatched Trip it was placed in over the full "
                "multi-wave lifecycle."),
        },
        "runs": runs,
        "aggregate": aggregate,
        "interpretation": (
            "Under the assumed compatibility-gated acceptance model, "
            "simulated acceptance at DMFE's own threshold of 70 was "
            f"{aggregate['headline_acceptance_at_threshold70_pct']['mean']}% "
            f"(mean across {REPEATS} repeats), well below the unselective "
            f"dispatch figure of {aggregate['dispatched_pct']['mean']}%.  "
            "Acceptance falls monotonically as the compatibility cutoff "
            "rises toward 90."),
        "limitations": (
            "Simulation only.  Not a human study; no user preference claims "
            "are made.  Acceptance probabilities are the model's assumptions "
            "(a compatibility-score cutoff), not measured behavior.  The "
            "'dispatched' baseline assumes unlimited fleet capacity over the "
            "day; acceptance under capacity pressure would be lower."),
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print("\n=== R1.5 Post-hoc Acceptance Filter (compat cutoff sweep) ===")
    header = "cutoff " + "".join(f"{c:>9}" for c in CUTOFFS)
    print("  " + header)
    print("  " + "".join(f"{'':>9}" for _ in CUTOFFS))
    for k in sorted(runs, key=lambda s: int(s)):
        r = runs[k]
        row = f"{r['seed']}  " + "".join(
            f"{r['compatibility_cutoff_sweep'][str(c)]['accepted_pct']:>9.1f}"
            for c in CUTOFFS)
        print("  " + row)
    aggrow = "mean  " + "".join(
        f"{sweep_agg[str(c)]['mean']:>9.1f}" for c in CUTOFFS)
    print("  " + aggrow)
    a = aggregate
    print(f"\n  dispatched (unselective): {a['dispatched_pct']['mean']}%")
    print(f"  headline acceptance @ threshold 70: "
          f"{a['headline_acceptance_at_threshold70_pct']['mean']}%")
    print(f"  priority-weighted @ 70: "
          f"{a['priority_weighted_acceptance_at70_pct']['mean']}%")
    print(f"  NOTE: simulation (assumed model), NOT a human study.")
    print(f"  wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
