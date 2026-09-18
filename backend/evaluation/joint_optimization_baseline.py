"""
ICCES-260 reviewer experiment — R1.3 Joint-Optimization Baseline
================================================================
Compares the DMFE's *sequential per-trip* dispatch approach against a
*genuinely joint* multi-vehicle PDPTW solved by a single OR-Tools
model over the full request set.

What DMFE does today (sequential)
    1. BatchGenerator pairs requests into batches (greedy disjoint).
    2. For each batch: select one vehicle+driver, solve a single-vehicle
       PDP with OR-Tools, dispatch the trip.
    Assignments are greedy -- earlier batches claim vehicles first, and
    each batch is solved independently.

What the baseline does (joint)
    For the SAME request set, a SINGLE OR-Tools model jointly:
      - assigns every request to a vehicle,
      - routes each vehicle's assigned requests in a globally optimal
        order (pickup-before-delivery, same vehicle),
      - enforces a per-vehicle capacity of ``CAP`` requests.
    We run CAP = 2 (exactly DMFE's max batch size) and, as an upper
    bound on joint value, CAP = 4.

Scope honesty (stated in every output):
    This baseline does NOT include the DMFE's 5-factor compatibility
    score, driver quality selection, or adaptive weight logic.  It solves
    the *routing and assignment sub-problem* jointly, which is the
    portion that the sequential greedy approach leaves suboptimal.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))
sys.path.insert(0, str(EVAL_DIR.parent))

from framework import (  # noqa: E402
    RESULTS_DIR,
    SYSTEM_CONFIG,
    ExperimentDB,
    WorkloadRunner,
)

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Vehicle, SimulationRequest, Trip  # noqa: E402
from app.engine.distance import haversine  # noqa: E402

from ortools.constraint_solver import pywrapcp, routing_enums_pb2  # noqa: E402

OUT_FILE = os.path.join(RESULTS_DIR, "r13_joint_optimization.json")
WORKLOADS = [50, 100]
CAPS = [2, 4]
ROAD_FACTOR = 1.25
SPEED_KMH = 25.0
CO2_FACTOR = 2.3


def _generate_pool(workload: int, seed: int, db) -> List[SimulationRequest]:
    from app.services.mock_adapters import generate_simulation_requests
    random.seed(seed)
    return generate_simulation_requests(
        count=workload, db=db,
        request_types={"ride": 0.40, "food": 0.40, "parcel": 0.20},
    )


def _fleet_from_db(db) -> List[Dict[str, Any]]:
    vehicles = db.query(Vehicle).filter(
        Vehicle.is_active.is_(True),
        Vehicle.status == "Available",
    ).all()
    return [
        {
            "id": v.id,
            "type": v.vehicle_type,
            "capacity": int(v.capacity or 1),
            "mileage_kmpl": float(v.mileage_kmpl or 15.0),
            "cost_per_km": float(v.cost_per_km or 10.0),
            "lat": float(v.current_lat or 11.0168),
            "lng": float(v.current_lng or 76.9558),
        }
        for v in vehicles
    ]


def _dist_m(lat1, lng1, lat2, lng2) -> int:
    return int(haversine(lat1, lng1, lat2, lng2) * ROAD_FACTOR * 1000.0)


def _solve_joint(
    requests: List[SimulationRequest],
    fleet: List[Dict[str, Any]],
    cap: int,
    time_limit_s: int = 30,
) -> Dict[str, Any]:
    """
    Joint multi-vehicle Pickup-and-Delivery model over the full request set.

    Model:
        Node 0 = depot (city centre).
        Nodes 2i+1 / 2i+2 = pickup / drop of request i.
        Total nodes = 1 + 2N.
        V = ceil(N / cap) vehicles, all start/end at the depot.
        Each vehicle serves at most `cap` requests (load = # pickups).

    The solver jointly decides which vehicle serves each request and the
    globally optimal route order (constraints: same vehicle for the
    pickup and drop, pickup before delivery, capacity cap).

    The OR-Tools solve runs in an isolated subprocess (see
    ``joint_optimization_worker.py``) so that a hard wall-clock timeout can
    be enforced.  OR-Tools' own first-solution search is non-deterministic
    and can occasionally loop without honouring its internal time limit, so
    the worker supplies a greedy feasible initial solution and runs only
    local search, and the parent process kills any runaway solve.
    """
    import json as _json
    import subprocess as _sp
    import tempfile as _tf

    n_req = len(requests)
    n_veh = (n_req + cap - 1) // cap
    n_nodes = 1 + 2 * n_req

    worker = os.path.join(EVAL_DIR, "joint_optimization_worker.py")
    workdir = _tf.gettempdir()
    in_json = os.path.join(workdir, f"r13_in_{os.getpid()}_{cap}.json")
    out_json = os.path.join(workdir, f"r13_out_{os.getpid()}_{cap}.json")

    payload = {
        "requests": [
            {
                "pu": [r.pickup_lat, r.pickup_lng],
                "do": [r.drop_lat, r.drop_lng],
            }
            for r in requests
        ],
        "fleet": [
            {
                "id": v["id"],
                "type": v["type"],
                "capacity": int(v["capacity"] or 1),
                "mileage_kmpl": float(v["mileage_kmpl"] or 15.0),
                "lat": float(v["lat"] or 11.0168),
                "lng": float(v["lng"] or 76.9558),
            }
            for v in fleet
        ],
        "cap": cap,
        "time_limit_s": time_limit_s,
    }

    _py = sys.executable
    hard_timeout = max(time_limit_s + 20, 45)

    try:
        with open(in_json, "w", encoding="utf-8") as fh:
            _json.dump(payload, fh)
        if os.path.exists(out_json):
            os.remove(out_json)
        t0 = time.perf_counter()
        try:
            _sp.run(
                [_py, worker, in_json, out_json],
                timeout=hard_timeout,
                cwd=str(EVAL_DIR.parent),
                capture_output=True,
            )
        except _sp.TimeoutExpired:
            return {
                "status": "TIMEOUT",
                "wall_s": round(time.perf_counter() - t0, 3),
                "objective_value": None,
                "solver_status": "hard_timeout",
                "n_vehicles_model": n_veh,
                "total_distance_km": None,
            }
        if not os.path.exists(out_json):
            return {
                "status": "FAILED",
                "wall_s": round(time.perf_counter() - t0, 3),
                "objective_value": None,
                "solver_status": "worker_error",
                "n_vehicles_model": n_veh,
                "total_distance_km": None,
            }
        with open(out_json, "r", encoding="utf-8") as fh:
            res = _json.load(fh)
        if res.get("total_distance_km") is None:
            res["wall_s"] = round(time.perf_counter() - t0, 3)
        return res
    finally:
        for p in (in_json, out_json):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


def _run_dmfe_sequential(workload: int, seed: int) -> Dict[str, Any]:
    exp = ExperimentDB()
    db = SessionLocal()
    try:
        exp.reset_schema()
        rng = random.Random(seed)
        exp.seed_system_config_with(db, dict(SYSTEM_CONFIG))
        exp.seed_fleet(db, rng)

        runner = WorkloadRunner(workload, seed=seed)
        runner.install_probes()
        runner.requests = _generate_pool(workload, seed, db)
        t0 = time.perf_counter()
        out = runner.run_pipeline(db)
        runner.complete_trips_real(db)
        wave_ids: List[int] = []
        waves = 0
        for _ in range(25):
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
        wall_s = time.perf_counter() - t0

        all_ids = out["trip_ids"] + wave_ids
        all_trips = db.query(Trip).filter(Trip.id.in_(all_ids)).all() if all_ids else []
        total_dist = sum(t.total_distance_km or 0 for t in all_trips)
        total_fuel = sum(t.fuel_l or 0 for t in all_trips)
        shared = sum(1 for t in all_trips if t.is_shared)

        return {
            "wall_s": round(wall_s, 3),
            "total_distance_km": round(total_dist, 2),
            "total_fuel_l": round(total_fuel, 3),
            "total_co2_kg": round(total_fuel * CO2_FACTOR, 3),
            "n_trips": len(all_trips),
            "n_shared_trips": shared,
            "n_individual_trips": len(all_trips) - shared,
        }
    finally:
        db.close()


def run_one_workload(workload: int, seed: int) -> Dict[str, Any]:
    print(f"\n--- R1.3 N={workload} (seed={seed}) ---")

    print("  Running DMFE sequential...")
    dmfe = _run_dmfe_sequential(workload, seed)
    print(f"  DMFE: {dmfe['n_trips']} trips "
          f"({dmfe['n_shared_trips']} shared), {dmfe['total_distance_km']} km, "
          f"{dmfe['total_fuel_l']} L")

    print("  Preparing joint baseline...")
    exp = ExperimentDB()
    db = SessionLocal()
    try:
        exp.reset_schema()
        rng = random.Random(seed)
        exp.seed_system_config_with(db, dict(SYSTEM_CONFIG))
        exp.seed_fleet(db, rng)
        reqs = _generate_pool(workload, seed, db)
        fleet = _fleet_from_db(db)
    finally:
        db.close()

    joint_results: Dict[str, Any] = {}
    for cap in CAPS:
        print(f"  Joint oracle (cap={cap} requests/vehicle)...")
        j = _solve_joint(reqs, fleet, cap=cap, time_limit_s=30)
        joint_results[f"cap_{cap}"] = {
            k: v for k, v in j.items() if k != "vehicle_routes_summary"
        }
        joint_results[f"cap_{cap}"]["n_routes"] = len(j["vehicle_routes_summary"])
        print(f"    status={j['status']}, {j['total_distance_km']} km, "
              f"{j['total_fuel_l']} L, {j['wall_s']:.1f}s, "
              f"served={j['n_requests_assigned']}/{len(reqs)}, "
              f"saving_vs_individual={j['distance_saving_vs_individual_pct']}%")

    # Comparison: DMFE vs joint-cap2 (same batch size) vs joint-cap4 (upper bound)
    j2 = joint_results["cap_2"]
    j4 = joint_results["cap_4"]
    dfe_dist = dmfe["total_distance_km"]

    def _safe(v):
        return v if v is not None else float("nan")

    def _pct(denom, diff):
        if not denom:
            return None
        return round(diff / denom * 100.0, 1)

    comparison = {
        "dmfe_distance_km": dfe_dist,
        "joint_cap2_distance_km": j2["total_distance_km"],
        "joint_cap4_distance_km": j4["total_distance_km"],
        "joint_cap2_better_than_dmfe_km": round(
            _safe(j2["total_distance_km"]) - dfe_dist, 2),
        "joint_cap2_better_than_dmfe_pct": _pct(
            dfe_dist, _safe(j2["total_distance_km"]) - dfe_dist),
        "joint_cap4_better_than_dmfe_km": round(
            _safe(j4["total_distance_km"]) - dfe_dist, 2),
        "joint_cap4_better_than_dmfe_pct": _pct(
            dfe_dist, _safe(j4["total_distance_km"]) - dfe_dist),
    }

    return {
        "seed": seed,
        "workload": workload,
        "fleet_size": len(fleet),
        "n_requests": len(reqs),
        "dmfe_sequential": dmfe,
        "joint_baseline": joint_results,
        "comparison": comparison,
        "scope_note": (
            "The joint baseline solves the multi-vehicle PDPTW routing and "
            "assignment sub-problem in a single OR-Tools model.  It does NOT "
            "include DMFE's 5-factor compatibility scoring, driver quality "
            "selection, or adaptive threshold logic.  The comparison isolates "
            "the value of joint vs sequential vehicle assignment at equal "
            "capacity (cap=2 equals DMFE's max batch size)."),
    }


def main() -> None:
    results: Dict[str, Dict[str, Any]] = {}
    for workload in WORKLOADS:
        seed = 1000 + workload
        results[str(workload)] = run_one_workload(workload, seed)

    output = {
        "experiment": "R1.3 joint-optimization baseline (OR-Tools VRPPD)",
        "reviewer_mapping": "R1.3",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workloads": WORKLOADS,
        "capacities": CAPS,
        "seed_convention": "seed = 1000 + workload",
        "results": results,
        "scope": (
            "Multi-vehicle Pickup-and-Delivery solved by OR-Tools as a single "
            "model over the full request set.  Jointly assigns requests to "
            "vehicles AND routes each vehicle optimally.  Cap = max requests "
            "per vehicle; cap=2 matches DMFE's max batch size, cap=4 is an "
            "upper bound on joint batching value.  Single fixed depot = city "
            "centre (11.0168 N, 76.9558 E).  Does NOT include DMFE "
            "compatibility scoring or driver selection."),
        "method_notes": (
            "Same fleet seeded by the evaluation harness and same request "
            "generator (40/40/20 ride/food/parcel).  Arc cost = road-adjusted "
            "haversine distance.  Constraints: pickup-before-delivery, same "
            "vehicle, capacity = CAP requests per vehicle.  Load dimension "
            "tracks number of pickups per vehicle.  Each routed vehicle "
            "starts AND returns to the central depot, so the joint distance "
            "includes return-leg deadhead that DMFE's per-trip distance "
            "figure does not - this biases joint numbers upward at low cap."),
        "limitations": (
            "Does not include DMFE's 5-factor compatibility, driver quality "
            "selection, or adaptive logic -- only the routing/assignment "
            "sub-problem.  Free-fleet mileage assumed for fuel.  Single "
            "central depot rather than per-vehicle starting positions.  "
            "Synthetic requests; not a real-world dispatch study."),
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    print(f"\n=== R1.3 ALL DONE -- wrote {OUT_FILE} ===")


if __name__ == "__main__":
    main()