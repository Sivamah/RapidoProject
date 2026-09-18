"""
ICCES-260 reviewer experiment — R1.5 Acceptance Simulation
==========================================================
A SIMULATION — NOT A HUMAN STUDY.

It models how many requests are accepted (feasibly paired + dispatched)
and fulfilled (completed through the trip lifecycle) under an explicitly
assumed acceptance model, across deterministic repeated simulation runs.

Explicit assumptions (the model)
--------------------------------
    1. Requests carry priority Low / Medium / High (the current application
       representation).  DMFE's priority scoring weights these 0.20 / 0.60 /
       1.00 respectively, so higher-priority requests are more likely to be
       selected into a compatible batch.
    2. A request is "accepted" when the current pipeline dispatches it into
       a shared or individual trip (assignment is the acceptance decision).
    3. An accepted request is "fulfilled" when its trip completes through
       the real trip lifecycle under the deterministic execution model.
    4. "Simulated acceptance rate" = share of requests that are fulfilled
       over the repeated runs.

We NEVER claim these numbers are measured human acceptance.  Statements
are phrased strictly as: "Under the assumed acceptance model, simulated
acceptance was X%."

Determinism
    Each of the REPEATS simulation runs uses a documented seed and the
    identical workload configuration; only the seed indexes the run.
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
    CO2_FACTOR,
    MAX_WAVES,
    SYSTEM_CONFIG,
    ExperimentDB,
    WorkloadRunner,
)

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import SimulationRequest, Trip  # noqa: E402

SEED_BASE = 1515
REPEATS = 5
WORKLOAD = 60
PRIORITY_WEIGHTS = {"Low": 0.20, "Medium": 0.60, "High": 1.00}
OUT_FILE = os.path.join(RESULTS_DIR, "r15_acceptance.json")


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
        # Each wave reseeds the module-global dispatch RNG and the runner's
        # independent execution RNG from the repeat seed + wave index so the
        # wave phase is reproducible run-to-run.
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

        # per-priority outcome (acceptance => fulfilled completion)
        by_priority: Dict[str, Dict[str, Any]] = {}
        for p in PRIORITY_WEIGHTS:
            by_priority[p] = {"total": 0, "accepted": 0, "fulfilled": 0}
        for r in reqs:
            p = r.priority if r.priority in by_priority else "Medium"
            by_priority[p]["total"] += 1
            if r.status in ("Assigned", "Completed"):
                by_priority[p]["accepted"] += 1
            if r.status == "Completed":
                by_priority[p]["fulfilled"] += 1

        completed_total = sum(
            1 for r in reqs if r.status == "Completed")
        accepted_total = sum(
            1 for r in reqs if r.status in ("Assigned", "Completed"))

        accepted_by_priority = {p: d["accepted"] for p, d in by_priority.items()}
        weights = [PRIORITY_WEIGHTS[p] for p in PRIORITY_WEIGHTS]
        # priority-weighted acceptance under the assumed model
        if sum(d["total"] for d in by_priority.values()) == 0:
            sim_acceptance = 0.0
        else:
            wsum = 0.0
            for p, d in by_priority.items():
                rate = d["accepted"] / d["total"] if d["total"] else 0.0
                wsum += PRIORITY_WEIGHTS[p] * rate
            sim_acceptance = wsum / sum(PRIORITY_WEIGHTS.values())

        return {
            "seed": seed,
            "requests": WORKLOAD,
            "per_priority": {
                p: {
                    "total": d["total"],
                    "accepted": d["accepted"],
                    "fulfilled": d["fulfilled"],
                    "simulated_acceptance_rate_pct": round(
                        d["accepted"] / d["total"] * 100.0, 1) if d["total"] else 0.0,
                } for p, d in by_priority.items()
            },
            "accepted_total": accepted_total,
            "completed_total": completed_total,
            "simulated_acceptance_rate_pct": round(
                accepted_total / WORKLOAD * 100.0, 1),
            "simulated_fulfillment_rate_pct": round(
                completed_total / WORKLOAD * 100.0, 1),
            "priority_weighted_acceptance_pct": round(sim_acceptance * 100.0, 1),
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

    # aggregate across repeats
    acc_rates = [r["simulated_acceptance_rate_pct"] for r in runs.values()]
    fulf_rates = [r["simulated_fulfillment_rate_pct"] for r in runs.values()]
    weighted_rates = [r["priority_weighted_acceptance_pct"] for r in runs.values()]

    def agg(vals: List[float]) -> Dict[str, float]:
        return {
            "mean": round(sum(vals) / len(vals), 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
        }

    aggregate = {
        "simulated_acceptance_rate_pct": agg(acc_rates),
        "simulated_fulfillment_rate_pct": agg(fulf_rates),
        "priority_weighted_acceptance_pct": agg(weighted_rates),
        "repeats": REPEATS,
    }

    result = {
        "experiment": "R1.5 acceptance simulation",
        "reviewer_mapping": "R1.5",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seed_base": SEED_BASE,
        "repeats": REPEATS,
        "workload": WORKLOAD,
        "mode": SYSTEM_CONFIG.get("admfe.mode", "adaptive"),
        "assumptions": {
            "human_study": False,
            "priority_weights": PRIORITY_WEIGHTS,
            "accepted_means_dispatched": (
                "A request is counted accepted when the pipeline dispatches it "
                "into a shared or individual trip (assignment is the "
                "acceptance decision)."),
            "fulfilled_means_completed": (
                "An accepted request is counted fulfilled when its trip "
                "completes through the real trip lifecycle under the "
                "deterministic execution model."),
            "model": (
                "Higher-priority requests carry higher scoring weight in DMFE "
                "(0.2/0.6/1.0), so they are more likely to be paired and "
                "dispatched.  All numbers below are SIMULATED outcomes of this "
                "model, not measured human acceptance."),
        },
        "runs": runs,
        "aggregate": aggregate,
        "interpretation": (
            "Under the assumed acceptance model (priority-weighted dispatch "
            "and completion through the trip lifecycle), simulated "
            f"acceptance was {aggregate['simulated_acceptance_rate_pct']['mean']}% "
            f"mean across {REPEATS} repeats."),
        "limitations": (
            "Simulation only.  Not a human study; no user preference "
            "claims are made.  Acceptance probabilities are the model's "
            "assumptions, not measured behavior."),
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print("\n=== R1.5 Acceptance Simulation ===")
    for k in sorted(runs, key=lambda s: int(s)):
        r = runs[k]
        print(f"  run seed={r['seed']}: accept%={r['simulated_acceptance_rate_pct']:5.1f} "
              f"fulfill%={r['simulated_fulfillment_rate_pct']:5.1f} "
              f"batch%={r['single_pass']['batching_rate_pct']:5.1f}")
    a = aggregate
    print(f"  aggregate: simulated acceptance "
          f"{a['simulated_acceptance_rate_pct']['mean']}% "
          f"(min {a['simulated_acceptance_rate_pct']['min']}%, "
          f"max {a['simulated_acceptance_rate_pct']['max']}%) over {REPEATS} repeats")
    print(f"  NOTE: simulation (assumed model), NOT a human study.")
    print(f"  wrote {OUT_FILE}")


if __name__ == "__main__":
    main()