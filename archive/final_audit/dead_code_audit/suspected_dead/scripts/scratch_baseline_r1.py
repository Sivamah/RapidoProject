import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from app.engine.optimizer import AIOrchestrator
from app.engine.distance import create_distance_matrix
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

def setup_dicts(n_req):
    requests = []
    vehicles = []
    import random
    random.seed(42)
    
    for i in range(n_req):
        requests.append({
            "id": f"req_{i}",
            "request_type": random.choices(["ride", "food", "parcel"], weights=[0.4, 0.4, 0.2])[0],
            "pickup_lat": 11.01 + random.uniform(-0.05, 0.05),
            "pickup_lng": 77.01 + random.uniform(-0.05, 0.05),
            "drop_lat": 11.01 + random.uniform(-0.05, 0.05),
            "drop_lng": 77.01 + random.uniform(-0.05, 0.05),
            "demand": 1
        })
        
    for i in range(60):
        vehicles.append({
            "id": f"drv_{i}",
            "capacity": 4,
            "efficiency": 15.0
        })
        
    return requests, vehicles

def test_baseline_comparison(n_req):
    print(f"\n=== Baseline Comparison (N={n_req}) ===")
    requests, vehicles = setup_dicts(n_req)
    
    legacy = AIOrchestrator(None, None, None)
    start = time.time()
    try:
        legacy_routes = legacy._optimize_with_ortools(requests, vehicles)
        legacy_time = time.time() - start
        
        legacy_served = sum(len(rt["requests"]) for rt in legacy_routes)
        legacy_dist = sum(rt.get("distance_m", 0) for rt in legacy_routes) / 1000.0
        print(f"AIOrchestrator N={n_req}: Time={legacy_time:.2f}s, Routes={len(legacy_routes)}, Served={legacy_served}, Dist={legacy_dist:.1f}km")
    except Exception as e:
        print(f"AIOrchestrator N={n_req} FAILED: {str(e)} (Time: {time.time() - start:.2f}s)")
        
if __name__ == "__main__":
    test_baseline_comparison(50)
    test_baseline_comparison(100)
    test_baseline_comparison(250)
