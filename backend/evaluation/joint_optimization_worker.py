"""
R1.3 subprocess worker: runs the OR-Tools joint VRPPD solve in an isolated
process so the parent can enforce a hard wall-clock timeout (OR-Tools' own
search can occasionally hang without honoring its time limit).
Usage: python joint_optimization_worker.py <in.json> <out.json>
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_BACKEND = str(Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.engine.distance import haversine  # noqa: E402
from ortools.constraint_solver import pywrapcp, routing_enums_pb2  # noqa: E402

ROAD_FACTOR = 1.25
CO2_FACTOR = 2.3
DEPOT = (11.0168, 76.9558)


def _dist_m(lat1, lng1, lat2, lng2) -> int:
    return int(haversine(lat1, lng1, lat2, lng2) * ROAD_FACTOR * 1000.0)


def solve(requests: List[Dict[str, Any]], fleet: List[Dict[str, Any]],
          cap: int, time_limit_s: int) -> Dict[str, Any]:
    n_req = len(requests)
    n_veh = (n_req + cap - 1) // cap
    n_nodes = 1 + 2 * n_req

    locations: List[Tuple[float, float]] = [DEPOT]
    for r in requests:
        locations.append(tuple(r["pu"]))
        locations.append(tuple(r["do"]))

    dist_mat = [[0] * n_nodes for _ in range(n_nodes)]
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i != j:
                dist_mat[i][j] = _dist_m(*locations[i], *locations[j])

    mgr = pywrapcp.RoutingIndexManager(n_nodes, n_veh, 0)
    routing = pywrapcp.RoutingModel(mgr)

    def arc_cb(from_idx, to_idx):
        return dist_mat[mgr.IndexToNode(from_idx)][mgr.IndexToNode(to_idx)]
    routing.SetArcCostEvaluatorOfAllVehicles(
        routing.RegisterTransitCallback(arc_cb))

    def load_cb(from_idx):
        node = mgr.IndexToNode(from_idx)
        return 1 if (node >= 1 and node % 2 == 1) else 0
    routing.AddDimension(routing.RegisterUnaryTransitCallback(load_cb),
                         0, cap, True, "Load")

    load_dim = routing.GetDimensionOrDie("Load")
    for i in range(n_req):
        p = mgr.NodeToIndex(2 * i + 1)
        d = mgr.NodeToIndex(2 * i + 2)
        routing.AddPickupAndDelivery(p, d)
        routing.solver().Add(routing.VehicleVar(p) == routing.VehicleVar(d))
        routing.solver().Add(load_dim.CumulVar(p) <= cap)

    # Greedy feasible initial solution; run only local search from it.
    initial_routes = []
    for start in range(0, n_req, cap):
        route = [0]
        for i in range(start, min(start + cap, n_req)):
            route.append(2 * i + 1)
            route.append(2 * i + 2)
        initial_routes.append(route)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC)
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC)
    params.time_limit.seconds = time_limit_s

    import time as _t
    t0 = _t.perf_counter()
    initial_solution = routing.ReadAssignmentFromRoutes(initial_routes, True)
    solution = routing.SolveFromAssignmentWithParameters(initial_solution, params)
    wall_s = _t.perf_counter() - t0

    if solution is None:
        return {
            "status": "INFEASIBLE", "wall_s": round(wall_s, 3),
            "objective_value": None,
            "solver_status": routing._status if hasattr(routing, "_status")
            else str(routing.status()),
        }

    fleet_sorted = sorted(fleet, key=lambda v: -v["capacity"])
    total_dist = 0
    vehicle_routes = []
    assigned = set()
    for v_idx in range(n_veh):
        route_nodes = []
        idx = routing.Start(v_idx)
        while not routing.IsEnd(idx):
            route_nodes.append(mgr.IndexToNode(idx))
            idx = solution.Value(routing.NextVar(idx))
        if not route_nodes or (len(route_nodes) == 1 and route_nodes[0] == 0):
            continue
        route_dist = 0
        for k in range(len(route_nodes) - 1):
            route_dist += dist_mat[route_nodes[k]][route_nodes[k + 1]]
        total_dist += route_dist
        reqs_in_route = set()
        for node in route_nodes:
            if node >= 1 and node % 2 == 1:
                reqs_in_route.add((node - 1) // 2)
                assigned.add((node - 1) // 2)
        used_ids = {vr["_fid"] for vr in vehicle_routes}
        veh = next((fv for fv in fleet_sorted if fv["id"] not in used_ids), fleet_sorted[0])
        km = route_dist / 1000.0
        vehicle_routes.append({
            "vehicle_id": veh["id"], "vehicle_type": veh["type"],
            "mileage_kmpl": veh["mileage_kmpl"],
            "requests_served": len(reqs_in_route),
            "request_indices": sorted(reqs_in_route),
            "distance_km": round(km, 2),
            "fuel_l": round(km / max(veh["mileage_kmpl"], 1.0), 3),
            "_fid": veh["id"],
        })

    total_km = total_dist / 1000.0
    total_fuel = sum(r["fuel_l"] for r in vehicle_routes)

    individual_km = sum(
        _dist_m(*locations[p], *locations[p + 1]) for p in range(1, n_nodes, 2)
    ) / 1000.0
    mileage = sorted(v["mileage_kmpl"] for v in fleet)
    median_mileage = mileage[len(mileage) // 2]
    individual_fuel = individual_km / max(median_mileage, 1.0)

    unassigned = [i for i in range(n_req) if i not in assigned]

    return {
        "status": "FEASIBLE" if not unassigned else "PARTIAL",
        "wall_s": round(wall_s, 3),
        "objective_value": int(solution.ObjectiveValue()),
        "n_vehicles_model": n_veh,
        "n_vehicles_used": len(vehicle_routes),
        "n_requests_assigned": len(assigned),
        "n_requests_unassigned": len(unassigned),
        "total_distance_km": round(total_km, 2),
        "total_fuel_l": round(total_fuel, 3),
        "total_co2_kg": round(total_fuel * CO2_FACTOR, 3),
        "average_requests_per_vehicle": round(
            len(assigned) / len(vehicle_routes), 2) if vehicle_routes else 0.0,
        "distance_saving_vs_individual_pct": round(
            (1.0 - total_km / individual_km) * 100.0, 1
        ) if individual_km > 0 else 0.0,
        "fuel_saving_vs_individual_pct": round(
            (1.0 - total_fuel / individual_fuel) * 100.0, 1
        ) if individual_fuel > 0 else 0.0,
        "individual_baseline_km": round(individual_km, 2),
        "individual_baseline_fuel_l": round(individual_fuel, 3),
        "vehicle_routes_summary": [
            {k: v for k, v in r.items() if k != "_fid"}
            for r in vehicle_routes
        ],
    }


def main() -> None:
    in_path, out_path = sys.argv[1], sys.argv[2]
    with open(in_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    result = solve(data["requests"], data["fleet"],
                   data["cap"], data["time_limit_s"])
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh)


if __name__ == "__main__":
    main()