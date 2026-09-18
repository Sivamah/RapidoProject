"""
ICCES-260 reviewer experiment — R2.1 Time-Window (max-delay) Sensitivity
=======================================================================
Sweeps the DMFE time-window constraint that the CURRENT implementation
actually consumes:

    SystemConfig  max_allowed_delay_min

across 10, 15, 20, 25, 30 minutes, at TWO workload sizes (N=50, N=100).

What this knob does in the current code
---------------------------------------
    * The pairing time-compatibility gate reads it as ``max_delay_min`` in
      scoring.time_window_score(ts1, ts2, max_delay_min) — pairs whose
      request_timestamp difference exceeds it are time-incompatible.
    * The routing rules (VRP_RULE_DEFAULTS.max_allowed_delay_min) and the
      pipeline's per-batch delay estimate use it as the delay budget.

There is NO per-request time-window column in the schema that DMFE
enforces (SimulationRequest.max_acceptable_delay_min exists but is never
read by the engine).  This experiment therefore sweeps the actual
configuration knob and does NOT introduce any fake request-level
time-window column.

Mechanism (so the sweep is real)
--------------------------------
    1. For each workload (50, 100) and each sweep value, seed the isolated
       evaluation SystemConfig with ``max_allowed_delay_min = <value>`` and
       call the project's own ``clear_config_cache()`` so the new value is
       picked up from the DB (config is TTL-cached).
    2. Regenerate a deterministic request set for that workload/sweep
       (same seed per workload across sweep points so only the knob
       changes for that workload).
    3. Run the CURRENT pipeline (single-pass + full-day waves).
    4. Record batching rate, shared/individual trips, avg delay, delay
       budget read-back, and completion rate.
    5. The delay-budget read-back (the value the engine saw) is recorded to
       prove the knob actually took effect.
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
from app.db.models import SimulationRequest, Trip, SystemConfig  # noqa: E402
from app.dmfe.compatibility import clear_config_cache, read_float_value  # noqa: E402

SWEEP_MIN = [10, 15, 20, 25, 30]
WORKLOADS = [50, 100]
SEED_FOR = {50: 2121, 100: 2122}
DELAY_KEY = "max_allowed_delay_min"
OUT_FILE = os.path.join(RESULTS_DIR, "r21_time_window_all.json")


def run_sweep_point(value: int, workload: int, seed: int) -> Dict[str, Any]:
    exp = ExperimentDB()
    db = SessionLocal()
    try:
        exp.reset_schema()
        config = dict(SYSTEM_CONFIG)
        config[DELAY_KEY] = str(value)
        exp.seed_system_config_with(db, config)
        rng = random.Random(seed)
        exp.seed_fleet(db, rng)

        # IMPORTANT: config is TTL-cached in the module; force a refresh so
        # the new value is actually consumed.
        clear_config_cache()

        from app.services.mock_adapters import generate_simulation_requests
        random.seed(seed)
        reqs = generate_simulation_requests(
            count=workload, db=db,
            request_types={"ride": 0.40, "food": 0.40, "parcel": 0.20},
        )
        if len(reqs) < workload:
            raise RuntimeError(
                f"Sweep {value} N={workload} got {len(reqs)}/{workload} "
                f"requests; aborting this sweep point (no fabricated rows).")

        # Prove the knob is what the engine sees: re-read after seeding+clear.
        seen = read_float_value(db, DELAY_KEY, 20.0)

        runner = WorkloadRunner(workload, seed=seed)
        runner.install_probes()
        runner.requests = reqs

        # Single-pass
        out = runner.run_pipeline(db)
        status_map = {r.id: r.status for r in reqs}
        single = runner.collect_metrics(db, out["trip_ids"], status_map)

        # Full-day waves.
        # Each wave reseeds the module-global dispatch RNG and the runner's
        # independent execution RNG from the sweep seed + wave index so the
        # wave phase is reproducible run-to-run.
        runner.complete_trips_real(db)
        waves = 0
        wave_ids: List[int] = []
        for _ in range(MAX_WAVES):
            pending = db.query(SimulationRequest).filter(
                SimulationRequest.status == "Pending").count()
            if pending == 0:
                break
            random.seed(seed + 1000 + waves)
            runner._exec_rng = random.Random(seed + 9000 + waves)
            wout = runner.run_pipeline(db)
            wave_ids.extend(wout["trip_ids"])
            waves += 1
            if not wout["trip_ids"]:
                break
            runner.complete_trips_real(db)

        all_ids = out["trip_ids"] + wave_ids
        wtrips = (db.query(Trip).filter(Trip.id.in_(all_ids)).all()
                  if all_ids else [])
        wfuel = sum(t.fuel_l or 0 for t in wtrips)
        wdist = sum(t.total_distance_km or 0 for t in wtrips)
        completed = sum(1 for r in reqs if r.status in ("Assigned", "Completed"))

        return {
            "sweep_value_min": value,
            "delay_budget_seen_by_engine_min": seen,
            "knob_took_effect": abs(seen - value) < 1e-6,
            "seed": seed,
            "requests": workload,
            "single_pass": {
                "processed": out["result"].requests_processed,
                "shared_trips": out["result"].shared_trips,
                "individual_trips": out["result"].individual_trips,
                "assignments_created": out["result"].assignments_created,
                "batching_rate_pct": single["batching_rate_pct"],
                "avg_delay_min": single["avg_delay_min"],
                "avg_utilization_pct": single["avg_utilization_pct"],
                "total_distance_km": single["total_distance_km"],
                "total_fuel_l": single["total_fuel_l"],
            },
            "waves": {
                "waves": waves,
                "trips_total": len(all_ids),
                "total_distance_km": round(wdist, 2),
                "total_fuel_l": round(wfuel, 2),
                "total_co2_kg": round(wfuel * CO2_FACTOR, 2),
                "requests_completed": completed,
                "requests_failed": workload - completed,
                "completion_rate_pct": round(completed / workload * 100.0, 1),
            },
        }
    finally:
        db.close()


def main() -> None:
    results_per_workload: Dict[str, Dict[str, Dict[str, Any]]] = {}
    all_took_effect = True
    for workload in WORKLOADS:
        seed = SEED_FOR.get(workload, 2100 + workload)
        sweep_out: Dict[str, Dict[str, Any]] = {}
        for v in SWEEP_MIN:
            sweep_out[str(v)] = run_sweep_point(v, workload, seed)
        results_per_workload[str(workload)] = sweep_out
        all_took_effect = all_took_effect and all(
            p["knob_took_effect"] for p in sweep_out.values())

    result = {
        "experiment": "R2.1 time-window (max delay) sensitivity",
        "reviewer_mapping": "R2.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": SYSTEM_CONFIG.get("admfe.mode", "adaptive"),
        "workloads": WORKLOADS,
        "sweep": SWEEP_MIN,
        "knob": {
            "config_key": DELAY_KEY,
            "what_it_controls": (
                "max pairwise request-timestamp difference allowed for a "
                "compatible pair (scoring.time_window_score) and the routing "
                "delay budget / per-batch delay estimate."),
            "fake_column_used": False,
        },
        "all_knob_values_took_effect": all_took_effect,
        "results": results_per_workload,
        "method_notes": (
            "For each workload, each sweep point reseeds "
            "SystemConfig.max_allowed_delay_min in the isolated evaluation "
            "DB and calls clear_config_cache() so the new value is actually "
            "read.  Requests are regenerated with the same deterministic "
            "seed per workload at every sweep point, so only the time-window "
            "knob changes between points.  The engine's read-back of the "
            "knob is recorded per point."),
        "limitations": (
            "The current engine has no per-request time-window column; the "
            "sweep targets the actual SystemConfig max-allowed-delay gate. "
            "Synthetic requests only."),
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print("\n=== R2.1 Time-Window Sensitivity ===")
    for workload in WORKLOADS:
        print(f"  --- N={workload} ---")
        for v in SWEEP_MIN:
            p = results_per_workload[str(workload)][str(v)]
            print(f"  max_delay={v:2d} min (engine saw {p['delay_budget_seen_by_engine_min']:4.1f}) "
                  f"batch%={p['single_pass']['batching_rate_pct']:5.1f} "
                  f"shared={p['single_pass']['shared_trips']:2d} "
                  f"dispatch%={p['waves']['completion_rate_pct']:5.1f} "
                  f"avg_delay={p['single_pass']['avg_delay_min']:5.2f}")
    print(f"  knob took effect at all points: {all_took_effect}  wrote {OUT_FILE}")


if __name__ == "__main__":
    main()