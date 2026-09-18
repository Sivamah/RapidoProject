"""
ICCES-260 reviewer experiment — R1.1 Robustness Sweep
====================================================
Synthetic robustness sweep across EIGHT demand x temporal profiles
(2 demand levels x 4 temporal demand shapes).  Every profile is executed
through the CURRENT DMFE pipeline; no profile is skipped and no metric is
fabricated.

Temporal profiles are implemented through the current request-timestamp
mechanism: the request generator produces the requests, then the harness
re-assigns each request_timestamp value from a deterministic, documented
offset for the profile.  This is the SAME field the DMFE time-compatibility
gate (time_window_score on pairwise request_timestamp differences) and the
routing time dimension read, so the profile genuinely changes what DMFE
sees.  It does NOT introduce a fake per-request time-window column.

Profiles
    demand level      : LOW (30 requests) / HIGH (120 requests)
    temporal shape    : morning_peak, midday_flat, evening_peak, night_sparse
    (peak shapes cluster request timestamps in a tight window -> high time
     compatibility; flat/sparse shapes spread them -> lower).

Limitation (kept explicit)
    This is a synthetic robustness sweep over synthetic requests, NOT real
    multi-city / real-world data.  It is evidence that the pipeline runs
    and reports consistently across demand/temporal stress, not real-world
    generalisation.

Determinism
    A documented per-profile seed drives request generation and the
    execution model; identical-seed reruns reproduce identical results.
"""

from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

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

SEED_BASE = 1111
OUT_FILE = os.path.join(RESULTS_DIR, "r11_robustness.json")

DEMAND_LEVELS = {"LOW": 30, "HIGH": 120}


def _times_morning_peak(base: datetime, n: int) -> List[datetime]:
    rng_seed = None  # offsets chosen via the profile's own deterministic seed
    rng = random.Random(99901)
    offs = sorted(rng.uniform(0, 30) for _ in range(n))   # 30-min burst
    return [base + timedelta(minutes=o) for o in offs]


def _times_midday_flat(base: datetime, n: int) -> List[datetime]:
    rng = random.Random(99902)
    offs = sorted(rng.uniform(0, 480) for _ in range(n))  # spread over 8 h
    return [base + timedelta(minutes=o) for o in offs]


def _times_evening_peak(base: datetime, n: int) -> List[datetime]:
    rng = random.Random(99903)
    offs = sorted(rng.uniform(0, 30) for _ in range(n))   # 30-min burst
    return [base + timedelta(hours=11, minutes=o) for o in offs]


def _times_night_sparse(base: datetime, n: int) -> List[datetime]:
    rng = random.Random(99904)
    offs = sorted(rng.uniform(0, 240) for _ in range(n))  # spread over 4 h
    return [base + timedelta(hours=17, minutes=o) for o in offs]


TEMPORAL_PROFILES: Dict[str, Callable[[datetime, int], List[datetime]]] = {
    "morning_peak": _times_morning_peak,
    "midday_flat": _times_midday_flat,
    "evening_peak": _times_evening_peak,
    "night_sparse": _times_night_sparse,
}

PROFILE_ORDER = ["morning_peak", "midday_flat", "evening_peak", "night_sparse"]


def run_profile(demand_key: str, tname: str, seed: int) -> Dict[str, Any]:
    """Run one demand x temporal profile and return its metrics.

    Fresh schema (and fresh session) per profile for full independence,
    exactly like framework.run_workload does."""
    exp = ExperimentDB()
    db = SessionLocal()
    try:
        count = DEMAND_LEVELS[demand_key]
        exp.reset_schema()
        config = dict(SYSTEM_CONFIG)
        exp.seed_system_config_with(db, config)
        rng = random.Random(seed)
        exp.seed_fleet(db, rng)

        from app.services.mock_adapters import generate_simulation_requests
        random.seed(seed)
        reqs = generate_simulation_requests(
            count=count, db=db,
            request_types={"ride": 0.40, "food": 0.40, "parcel": 0.20},
        )
        if len(reqs) < count:
            raise RuntimeError(
                f"Profile {demand_key}/{tname} got {len(reqs)}/{count} requests; "
                f"aborting profile (no fabricated rows).")

        # Apply the temporal profile to the CURRENT request_timestamp field.
        base = datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc)
        times = TEMPORAL_PROFILES[tname](base, len(reqs))
        for r, ts in zip(reqs, times):
            r.request_timestamp = ts
        db.commit()

        runner = WorkloadRunner(count, seed=seed)
        runner.install_probes()
        runner.requests = reqs

        # Single-pass
        out = runner.run_pipeline(db)
        status_map = {r.id: r.status for r in reqs}
        single = runner.collect_metrics(db, out["trip_ids"], status_map)

        # Full-day waves.
        # NOTE: each wave reseeds the module-global dispatch RNG and the
        # runner's independent execution RNG from the profile seed + wave
        # index.  This makes the wave phase reproducible run-to-run (the
        # real pipeline otherwise advances both RNGs across wave iterations
        # and driver-availability racing in later waves is not stable).
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
        wdist = sum(t.total_distance_km or 0 for t in wtrips)
        wfuel = sum(t.fuel_l or 0 for t in wtrips)
        completed = sum(1 for r in reqs if r.status in ("Assigned", "Completed"))

        return {
            "demand_level": demand_key,
            "temporal_profile": tname,
            "seed": seed,
            "requests": count,
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
                "co2_emitted_kg": single["co2_emitted_kg"],
            },
            "waves": {
                "waves": waves,
                "trips_total": len(all_ids),
                "total_distance_km": round(wdist, 2),
                "total_fuel_l": round(wfuel, 2),
                "total_co2_kg": round(wfuel * CO2_FACTOR, 2),
                "requests_completed": completed,
                "requests_failed": count - completed,
                "completion_rate_pct": round(completed / count * 100.0, 1),
            },
        }
    finally:
        db.close()


def main() -> None:
    results: Dict[str, Dict[str, Any]] = {}
    for di, demand_key in enumerate(["LOW", "HIGH"]):
        for ti, tname in enumerate(PROFILE_ORDER):
            seed = SEED_BASE + di * 100 + ti
            results[f"{demand_key}:{tname}"] = run_profile(demand_key, tname, seed)
    # run_profile resets the schema per profile, so profiles were run on
    # fresh isolated schemas.  All 8 were executed; none skipped.

    summary = {
        "demand_levels": list(DEMAND_LEVELS.keys()),
        "temporal_profiles": PROFILE_ORDER,
        "profile_count": len(results),
    }

    result = {
        "experiment": "R1.1 robustness sweep (8 demand x temporal profiles)",
        "reviewer_mapping": "R1.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seeds": {k: v["seed"] for k, v in results.items()},
        "summary": summary,
        "profiles": results,
        "method_notes": (
            "Temporal profiles are applied to the request_timestamp field "
            "that the current DMFE time-compatibility gate and routing time "
            "dimension read.  No fake per-request time-window column is "
            "introduced.  All 8 profiles executed; none skipped."),
        "limitations": (
            "Synthetic robustness sweep over synthetic requests, not real "
            "multi-city / real-world data.  completion_rate_pct counts "
            "DISPATCHED requests (Assigned|Completed), i.e. dispatch "
            "success, not a finished-trip rate."),
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print("\n=== R1.1 Robustness Sweep ===")
    for k, v in results.items():
        w = v["waves"]
        print(f"  {k:26s}: reqs={v['requests']:3d} batch%={v['single_pass']['batching_rate_pct']:5.1f} "
              f"dispatch%={w['completion_rate_pct']:5.1f} "
              f"delay={v['single_pass']['avg_delay_min']:5.2f} waves={w['waves']}")
    print(f"  profiles executed: {len(results)}/8  wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
