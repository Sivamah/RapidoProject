"""
ICCES-260 reviewer experiment — R1.4 Per-Service Breakdown
==========================================================
Reports separate operational outcomes for the three service categories the
platform represents natively:

    ride   -> passenger mobility
    food   -> food delivery
    parcel -> parcel delivery

The experiment runs FOUR deterministic workloads (N = 50, 100, 250, 500)
through the current DMFE pipeline (single-pass dispatch + multi-wave
full-day simulation) using the *existing* framework, then re-aggregates
the stored results by service type.

Service labels are exactly the current application representation:
`SimulationRequest.request_type` in {"ride", "food", "parcel"}.  No
commercial provider names appear in any output.

Database isolation:
    This harness does not touch the production / development database
    (dmfe_dev.db).  It re-uses the evaluation harness's isolated SQLite
    database (backend/evaluation/experiments/eval.db), which is reset
    (drop_all + create_all) for every workload.

Determinism:
    Seed = 1000 + workload for each run, matching the convention in
    run_admfe_experiments.py.  Identical-seed reruns reproduce identical
    core results.

Reconciliation guarantee:
    Per-service request counts sum to the overall total and per-service
    dispatched request counts sum to the overall dispatched total.  Any
    mismatch fails loudly.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(EVAL_DIR.parent))  # backend root, for `app` / `framework`

# Must be set before importing app modules (framework sets it for its own db).
from framework import (  # noqa: E402  (sets DATABASE_URL before app import)
    EVAL_DB_PATH,
    EXPERIMENTS_DIR,
    RESULTS_DIR,
    FLEET_SIZE,
    SYSTEM_CONFIG,
    ExperimentDB,
    WorkloadRunner,
)

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import SimulationRequest, Trip, SystemConfig  # noqa: E402

# Service labels — exactly the current application representation.
SERVICES: List[str] = ["ride", "food", "parcel"]

# Workload sizes to evaluate (matching the main evaluation harness).
WORKLOADS: List[int] = [50, 100, 250, 500]
DEFAULT_MIX = {"ride": 0.40, "food": 0.40, "parcel": 0.20}
OUT_FILE = os.path.join(RESULTS_DIR, "r14_per_service_all.json")


def _dominant_service(request_ids: List[int],
                      id_to_type: Dict[int, str]) -> str:
    """Most frequent request_type among a trip's requests (tie -> first)."""
    counts: Dict[str, int] = {}
    for rid in request_ids:
        t = id_to_type.get(rid, "ride")
        counts[t] = counts.get(t, 0) + 1
    if not counts:
        return "ride"
    return max(counts, key=lambda k: (counts[k], -SERVICES.index(k)))


def _avg(vals: List[float]) -> float:
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def _run_workload_pipeline(db, runner: WorkloadRunner) -> Dict[str, Any]:
    """Single-pass + full-day (waves) run; returns the same shaped payload the
    framework produces, plus access to the live DB for per-service grouping.

    NOTE on overall vs per-service consistency: the per-service block
    aggregates over ALL dispatched trips (single-pass + full-day waves),
    because DMFE dispatches some requests only in later waves.  To keep the
    reported `overall` totals consistent with the per-service sums, the
    overall block is computed from the SAME full trip set (`all_trip_ids`),
    not just the single-pass trips."""
    out = runner.run_pipeline(db)
    status_map = {r.id: r.status for r in runner.requests}
    single = runner.collect_metrics(db, out["trip_ids"], status_map)
    batch_m = runner.batch_metrics(db)
    baseline = runner.compute_baseline(db)
    wave_out = runner.run_waves(db)
    all_ids = out["trip_ids"] + runner.wave_trip_ids

    # Overall metrics over the full (single-pass + waves) trip set, so they
    # are directly comparable to the per-service sums.
    all_trips = (
        db.query(Trip).filter(Trip.id.in_(all_ids)).all() if all_ids else []
    )
    all_shared = [t for t in all_trips if t.is_shared]
    all_individual = [t for t in all_trips if not t.is_shared]
    overall_trips = {
        "trips": len(all_trips),
        "shared_trips": len(all_shared),
        "individual_trips": len(all_individual),
        "batching_rate_pct": round(
            len(all_shared) / len(all_trips) * 100.0, 1) if all_trips else 0.0,
        "total_distance_km": round(
            sum(t.total_distance_km or 0 for t in all_trips), 2),
        "total_fuel_l": round(sum(t.fuel_l or 0 for t in all_trips), 2),
        "avg_utilization_pct": round(
            (sum(t.utilization_pct or 0 for t in all_trips) / len(all_trips)), 2)
            if all_trips else 0.0,
        "avg_delay_min": round(
            (sum(t.max_delay_min or 0 for t in all_trips) / len(all_trips)), 2)
            if all_trips else 0.0,
    }

    return {
        "single_pass": {
            "requests_processed": out["result"].requests_processed,
            "shared_trips": out["result"].shared_trips,
            "individual_trips": out["result"].individual_trips,
            "assignments_created": out["result"].assignments_created,
            "unassigned_count": len(out["result"].unassigned),
            "trips": single,
            "batches": batch_m,
        },
        "baseline": baseline,
        "waves": {
            "waves": wave_out["waves"],
            "trips_total": len(all_ids),
        },
        "overall_trips": overall_trips,
        "all_trip_ids": all_ids,
    }


def _build_per_service(db, runner: WorkloadRunner,
                       all_trip_ids: List[int]) -> Dict[str, Any]:
    """Re-aggregate request- and trip-level outcomes by service."""
    requests = runner.requests
    id_to_type: Dict[int, str] = {r.id: r.request_type for r in requests}
    total = len(requests)

    # Request-level: dispatch status per request.
    req_out = {s: {"total": 0, "dispatched": 0, "pending": 0, "rejected": 0}
               for s in SERVICES}
    for r in requests:
        s = r.request_type
        if s not in req_out:
            s = "ride"  # defensive: unknown service falls back consistently
        req_out[s]["total"] += 1
        status = (r.status or "Pending")
        if status in ("Assigned", "Completed"):
            req_out[s]["dispatched"] += 1
        elif status == "Rejected":
            req_out[s]["rejected"] += 1
        else:
            req_out[s]["pending"] += 1

    # Trip-level: attribute each trip to its dominant service.
    trips = (
        db.query(Trip).filter(Trip.id.in_(all_trip_ids)).all() if all_trip_ids else []
    )
    trip_out = {
        s: {"trips": 0, "shared_trips": 0, "individual_trips": 0,
            "total_distance_km": 0.0, "total_fuel_l": 0.0,
            "utilization": [], "delay_min": []}
        for s in SERVICES
    }
    shared_trip_request_ids: Dict[int, set] = {}
    for t in trips:
        try:
            rid_list: List[int] = json.loads(t.request_ids_json or "[]")
        except Exception:
            rid_list = []
        ds = _dominant_service(rid_list, id_to_type)
        row = trip_out[ds]
        row["trips"] += 1
        if t.is_shared:
            row["shared_trips"] += 1
            for rid in rid_list:
                shared_trip_request_ids.setdefault(rid, set()).add(t.id)
        else:
            row["individual_trips"] += 1
        row["total_distance_km"] += t.total_distance_km or 0
        row["total_fuel_l"] += (t.fuel_l or 0)
        row["utilization"].append(t.utilization_pct or 0.0)
        row["delay_min"].append(t.max_delay_min or 0.0)

    # Request-level shared vs individual attribution (no double counting).
    for s in SERVICES:
        o = req_out[s]
        o["shared_requests"] = 0
        o["individual_requests"] = 0
        for r in requests:
            if r.request_type == s and r.id in shared_trip_request_ids:
                o["shared_requests"] += 1
            elif r.request_type == s and r.status in ("Assigned", "Completed") \
                    and r.id not in shared_trip_request_ids:
                o["individual_requests"] += 1

    per_service: Dict[str, Dict[str, Any]] = {}
    for s in SERVICES:
        tr = trip_out[s]
        ro = req_out[s]
        per_service[s] = {
            "requests": ro["total"],
            "dispatched_requests": ro["dispatched"],
            "pending_requests": ro["pending"],
            "rejected_requests": ro["rejected"],
            "assignment_rate_pct": round(
                ro["dispatched"] / ro["total"] * 100.0, 1) if ro["total"] else 0.0,
            "shared_requests": ro["shared_requests"],
            "individual_requests": ro["individual_requests"],
            "trips": tr["trips"],
            "shared_trips": tr["shared_trips"],
            "individual_trips": tr["individual_trips"],
            "batching_rate_pct": round(
                tr["shared_trips"] / tr["trips"] * 100.0, 1) if tr["trips"] else 0.0,
            "total_distance_km": round(tr["total_distance_km"], 2),
            "total_fuel_l": round(tr["total_fuel_l"], 2),
            "avg_utilization_pct": _avg(tr["utilization"]),
            "avg_delay_min": _avg(tr["delay_min"]),
        }

    # Reconciliation — totals across services must equal overall totals.
    total_requests = sum(per_service[s]["requests"] for s in SERVICES)
    total_dispatched = sum(per_service[s]["dispatched_requests"] for s in SERVICES)
    total_trips = sum(per_service[s]["trips"] for s in SERVICES)
    total_shared = sum(per_service[s]["shared_trips"] for s in SERVICES)
    total_individual = sum(per_service[s]["individual_trips"] for s in SERVICES)
    recon = {
        "requests_total": total_requests,
        "overall_requests": total,
        "requests_match": total_requests == total,
        "dispatched_total": total_dispatched,
        "overall_dispatched": sum(
            1 for r in requests if r.status in ("Assigned", "Completed")),
        "trips_total": total_trips,
        "trips_in_db": len(trips),
        "shared_total": total_shared,
        "individual_total": total_individual,
        "reconciled": (
            total_requests == total
            and total_dispatched == sum(
                1 for r in requests if r.status in ("Assigned", "Completed"))
            and (total_shared + total_individual) == len(trips)
        ),
    }
    return {"per_service": per_service, "reconciliation": recon}


def run_one_workload(workload: int, seed: int) -> Dict[str, Any]:
    """Run a single workload and return the full result dict."""
    exp = ExperimentDB()
    db = SessionLocal()
    try:
        exp.reset_schema()

        effective_config = dict(SYSTEM_CONFIG)
        rng = random.Random(seed)
        exp.seed_system_config_with(db, effective_config)
        exp.seed_fleet(db, rng)

        random.seed(seed)
        from app.services.mock_adapters import generate_simulation_requests

        # Deterministic per-service request counts (round-robin by mix).
        requested = []
        for s in SERVICES:
            n = max(1, round(workload * DEFAULT_MIX[s]))
            requested.append((s, n))
        # Adjust so the sum equals workload exactly.
        diff = workload - sum(n for _, n in requested)
        requested[-1] = (requested[-1][0], requested[-1][1] + diff)
        request_types = {s: n for s, n in requested}

        reqs = generate_simulation_requests(
            count=workload, db=db, request_types=request_types,
        )
        if len(reqs) < workload:
            raise RuntimeError(
                f"generate_simulation_requests returned {len(reqs)} requests "
                f"but {workload} were requested. Aborting: no fabrication of "
                f"missing rows.")

        runner = WorkloadRunner(workload, seed=seed)
        runner.install_probes()
        runner.requests = reqs
        t0 = time.perf_counter()
        payload = _run_workload_pipeline(db, runner)
        wall_s = time.perf_counter() - t0

        service = _build_per_service(db, runner, payload["all_trip_ids"])
        recon = service["reconciliation"]
        if not recon["reconciled"]:
            raise RuntimeError(
                f"Per-service totals do not reconcile for N={workload}: "
                f"{recon}. Refusing to write an inconsistent result.")

        overall = payload["overall_trips"]
        return {
            "seed": seed,
            "mode": SYSTEM_CONFIG.get("admfe.mode", "adaptive"),
            "workload": {"total_requests": workload,
                         "request_mix": {s: n for s, n in requested}},
            "parameters": {
                "single_pass_waves": True,
                "fleet_size": FLEET_SIZE,
                "service_types": SERVICES,
                "commercial_names_used": False,
            },
            "overall": {
                "requests": workload,
                "dispatched_requests": recon["dispatched_total"],
                "assignment_rate_pct": round(
                    recon["dispatched_total"] / workload * 100.0, 1),
                "trips": overall["trips"],
                "shared_trips": overall["shared_trips"],
                "individual_trips": overall["individual_trips"],
                "batching_rate_pct": overall["batching_rate_pct"],
                "total_distance_km": overall["total_distance_km"],
                "total_fuel_l": overall["total_fuel_l"],
                "avg_utilization_pct": overall["avg_utilization_pct"],
                "avg_delay_min": overall["avg_delay_min"],
            },
            "per_service": service["per_service"],
            "reconciliation": {k: v for k, v in recon.items()
                               if k not in ("requests_match",)},
            "wall_s": round(wall_s, 3),
        }
    finally:
        db.close()


def main() -> None:
    all_results: Dict[str, Dict[str, Any]] = {}
    for workload in WORKLOADS:
        seed = 1000 + workload
        print(f"\n--- R1.4 workload N={workload} (seed={seed}) ---")
        result = run_one_workload(workload, seed)
        all_results[str(workload)] = result

        print(f"  mode={result['mode']}")
        for s in SERVICES:
            row = result["per_service"][s]
            print(f"  {s:7s}: reqs={row['requests']:3d} dispatched={row['dispatched_requests']:3d} "
                  f"assign%={row['assignment_rate_pct']:5.1f} trips={row['trips']:3d} "
                  f"shared={row['shared_trips']:2d} batch%={row['batching_rate_pct']:5.1f} "
                  f"delay={row['avg_delay_min']:5.2f}")
        print(f"  overall: trips={result['overall']['trips']} "
              f"batch%={result['overall']['batching_rate_pct']} "
              f"dist={result['overall']['total_distance_km']} km "
              f"fuel={result['overall']['total_fuel_l']} L")
        print(f"  reconciliation OK: {result['reconciliation']['reconciled']}")
        print(f"  wall time: {result['wall_s']:.1f}s")

    output = {
        "experiment": "R1.4 per-service breakdown (multi-workload)",
        "reviewer_mapping": "R1.4",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workloads": WORKLOADS,
        "request_mix": DEFAULT_MIX,
        "seed_convention": "seed = 1000 + workload",
        "results": all_results,
        "method_notes": (
            "Service categories are ride/food/parcel exactly as stored in "
            "SimulationRequest.request_type. Trips are attributed to their "
            "dominant (most-frequent) service. Shared-trip request counts "
            "are attributed without double counting. Totals reconcile per "
            "workload. Fuel/CO2 per-service allocation is intentionally not "
            "reported because a shared trip has no principled per-leg cost "
            "allocation."),
        "limitations": (
            "Synthetic requests; not a measure of real-world service "
            "fixtures. Fuel/CO2 remain unsplit because a shared trip has "
            "no principled per-leg cost allocation."),
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    print(f"\n=== R1.4 ALL DONE — wrote {OUT_FILE} ===")


if __name__ == "__main__":
    main()
