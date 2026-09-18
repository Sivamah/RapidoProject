"""
Scalability benchmark (read-only) — measures the ACTUAL project (backend/).

Workloads: 100, 150, 250 requests.  Each run 3 times (deterministic, distinct
seeds).  Reports mean / min / max for:

    - DMFE evaluation time        (total across CompatibilityCalculator.compute)
    - batch formation time        (BatchGenerator.create_feasible_batches)
    - dispatch time               (pipeline dispatch_trip)
    - total pipeline time         (wall clock of PipelineRunner.run)
    - compatibility pairs evaluated (pairs passed to compute in the pipeline)
    - batches created             (shared batches persisted as Compatible)
    - dispatched trips            (shared + individual)
    - unassigned requests
    - database queries

No source code (A-DMFE, scoring, batching, OR-Tools) is modified.  This script
only adds timing/counting probes around the existing engine entry points and
uses the platform's own request generator + a deterministic seeded fleet.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
import time
from typing import Any, Dict, List

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EVAL_DIR)
sys.path.insert(0, os.path.dirname(EVAL_DIR))  # backend root for `app` package

from sqlalchemy.orm import Session  # noqa: E402

from framework import (  # noqa: E402
    EVAL_DB_PATH, EXPERIMENTS_DIR, RESULTS_DIR, FLEET_SIZE, REQUEST_MIX,
    SYSTEM_CONFIG, WorkloadRunner, ExperimentDB, QueryCounter, Probe,
    CO2_FACTOR,
)
from app.dmfe.compatibility import CompatibilityCalculator  # noqa: E402
from app.db.models import Trip  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402

WORKLOADS = [100, 150, 250]
REPS = 3


class BenchmarkRunner(WorkloadRunner):
    """Adds DMFE-evaluation timing + per-run pair counting to the stock runner."""

    def __init__(self, workload: int, seed: int) -> None:
        super().__init__(workload, seed)
        self.dmfe_probe = Probe()
        # count compatibility score computations that actually ran (compute()).
        # `evaluated_pairs` is incremented inside the wrapped compute.
        self.evaluated_pairs = 0

    def install_probes(self) -> None:
        super().install_probes()

        original_compute = CompatibilityCalculator.compute

        def wrapped_compute(self_obj, requests, db, **kwargs):
            self.evaluated_pairs += 1
            t0 = time.perf_counter()
            try:
                return original_compute(self_obj, requests, db, **kwargs)
            finally:
                self.dmfe_probe.times.append(time.perf_counter() - t0)

        CompatibilityCalculator.compute = wrapped_compute
        self._original_compute = original_compute

    def restore_probes(self) -> None:
        if hasattr(self, "_original_compute"):
            CompatibilityCalculator.compute = self._original_compute


def run_benchmark_workload(workload: int, seed: int) -> Dict[str, Any]:
    exp = ExperimentDB()
    db = SessionLocal()
    try:
        exp.reset_schema()
        rng = random.Random(seed)
        effective_config = dict(SYSTEM_CONFIG)
        exp.seed_system_config_with(db, effective_config)
        exp.seed_fleet(db, rng)

        runner = BenchmarkRunner(workload, seed=seed)
        runner.install_probes()
        requests = runner.generate_requests(db)
        dist = {"ride": 0, "food": 0, "parcel": 0}
        for r in requests:
            dist[r.request_type] = dist.get(r.request_type, 0) + 1

        out = runner.run_pipeline(db)
        status_map = {r.id: r.status for r in requests}
        pipeline_s = out["wall_s"]

        dmfe_total_s = round(runner.dmfe_probe.total_s, 4)
        dmfe_calls = len(runner.dmfe_probe.times)
        dmfe_avg_ms = round(runner.dmfe_probe.avg_ms(), 3)

        metrics = runner.collect_metrics(db, out["trip_ids"], status_map)
        driver_m = runner.driver_metrics(db, out["trip_ids"])
        batch_m = runner.batch_metrics(db)

        # dispatch / batch / total / sql pulled from the stock timing snapshot
        snap = runner.timing_snapshot()

        wave_out = runner.run_waves(db)
        all_trip_ids = out["trip_ids"] + runner.wave_trip_ids
        wave_trips = (
            db.query(Trip).filter(Trip.id.in_(all_trip_ids)).all()
            if all_trip_ids else []
        )
        wave_dist = sum(t.total_distance_km or 0 for t in wave_trips)
        wave_fuel = sum(t.fuel_l or 0 for t in wave_trips)
        wave_completed = sum(
            1 for r in requests if r.status in ("Assigned", "Completed")
        )
        waves_metrics = {
            "waves": wave_out["waves"],
            "trips_total": len(runner.wave_trip_ids),
            "total_distance_km": round(wave_dist, 2),
            "total_fuel_l": round(wave_fuel, 2),
            "total_co2_kg": round(wave_fuel * CO2_FACTOR, 2),
            "requests_completed": wave_completed,
            "requests_failed": len(requests) - wave_completed,
            "completion_rate_pct": round(
                wave_completed / len(requests) * 100.0, 1),
            "sql_queries_total": runner.wave_sql_queries,
        }

        # restore the compute method before metrics that call it again
        runner.restore_probes()

        return {
            "workload": workload,
            "seed": seed,
            "request_mix": dist,
            "fleet_size": FLEET_SIZE,
            "single_pass": {
                "requests_processed": out["result"].requests_processed,
                "shared_trips": out["result"].shared_trips,
                "individual_trips": out["result"].individual_trips,
                "assignments_created": out["result"].assignments_created,
                "dispatched_trips": (out["result"].shared_trips
                                     + out["result"].individual_trips),
                "unassigned_count": len(out["result"].unassigned),
                "trips": metrics,
                "drivers": driver_m,
                "batches": batch_m,
            },
            "timing": {
                "pipeline_total_s": round(pipeline_s, 3),
                "dmfe_eval_total_s": dmfe_total_s,
                "dmfe_eval_calls": dmfe_calls,
                "dmfe_eval_avg_ms": dmfe_avg_ms,
                "batch_formation_total_s": snap["batch_formation_total_s"],
                "dispatch_total_s": snap["dispatch_total_s"],
                "dispatch_calls": snap["dispatch_calls"],
                "sql_queries": out.get("sql_queries", 0),
                "dmfe_share_pct": round(
                    dmfe_total_s / pipeline_s * 100.0, 1) if pipeline_s > 0 else 0.0,
                "batch_share_pct": round(
                    snap["batch_formation_total_s"] / pipeline_s * 100.0, 1)
                    if pipeline_s > 0 else 0.0,
            },
            "compat": {
                "pairs_evaluated": runner.evaluated_pairs,
            },
            "waves": waves_metrics,
        }
    finally:
        runner.restore_probes()
        db.close()


def agg(name: str, values: List[float]) -> Dict[str, Any]:
    n = len(values)
    return {
        "mean": round(statistics.mean(values), 3) if n else 0.0,
        "min": round(min(values), 3) if n else 0.0,
        "max": round(max(values), 3) if n else 0.0,
    }


def pull(results: List[Dict], path: str) -> List[float]:
    out = []
    for r in results:
        cur: Any = r
        for part in path.split("."):
            cur = cur[part]
        out.append(float(cur))
    return out


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_agg: Dict[str, Any] = {}
    per_run: Dict[int, List[Dict]] = {w: [] for w in WORKLOADS}
    flattened: List[Dict] = []

    for workload in WORKLOADS:
        print(f"[bench] workload={workload} ...", flush=True)
        for rep in range(1, REPS + 1):
            seed = 1000 + workload * 10 + rep
            print(f"  rep {rep}/{REPS} seed={seed}", flush=True)
            res = run_benchmark_workload(workload, seed)
            per_run[workload].append(res)
            flattened.append(res)
        print(f"[bench] workload={workload} done", flush=True)

    for workload in WORKLOADS:
        rs = per_run[workload]
        all_agg[str(workload)] = {
            "dmfe_eval_time_s": agg("dmfe", pull(rs, "timing.dmfe_eval_total_s")),
            "batch_formation_time_s": agg(
                "batch", pull(rs, "timing.batch_formation_total_s")),
            "dispatch_time_s": agg("dispatch", pull(rs, "timing.dispatch_total_s")),
            "pipeline_total_time_s": agg(
                "pipeline", pull(rs, "timing.pipeline_total_s")),
            "compat_pairs_evaluated": agg(
                "pairs", pull(rs, "compat.pairs_evaluated")),
            "batches_created": agg(
                "batches", pull(rs, "single_pass.batches.shared_batches_created")),
            "dispatched_trips": agg(
                "trips", pull(rs, "single_pass.dispatched_trips")),
            "unassigned_requests": agg(
                "unassigned", pull(rs, "single_pass.unassigned_count")),
            "database_queries": agg("queries", pull(rs, "timing.sql_queries")),
        }

    summary = {"workloads": WORKLOADS, "reps": REPS, "aggregates": all_agg}
    out_file = os.path.join(RESULTS_DIR, "scalability_benchmark_100_150_250.json")
    with open(out_file, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\nWrote {out_file}")

    # pretty-print mean table
    print("\n=== SCALABILITY BENCHMARK (3 reps, mean / min / max) ===")
    hdr = f"{'Metric':<28}" + "".join(f"{str(w):>22}" for w in WORKLOADS)
    print(hdr)
    print("-" * len(hdr))
    labels = {
        "dmfe_eval_time_s": "DMFE eval time (s)",
        "batch_formation_time_s": "Batch formation (s)",
        "dispatch_time_s": "Dispatch (s)",
        "pipeline_total_time_s": "Pipeline total (s)",
        "compat_pairs_evaluated": "Compat pairs evaluated",
        "batches_created": "Batches created",
        "dispatched_trips": "Dispatched trips",
        "unassigned_requests": "Unassigned requests",
        "database_queries": "DB queries",
    }
    for key, label in labels.items():
        cells = []
        for w in WORKLOADS:
            a = all_agg[str(w)][key]
            cells.append(f"{a['mean']:.3f} / {a['min']:.3f} / {a['max']:.3f}"
                         if isinstance(a["mean"], float)
                         else f"{a['mean']:.1f} / {a['min']:.1f} / {a['max']:.1f}")
        print(f"{label:<28}" + "".join(f"{c:>22}" for c in cells))

    print("\nFull per-run detail in", out_file)


if __name__ == "__main__":
    main()
