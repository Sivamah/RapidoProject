import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from app.db.models import SimulationRequest
from app.dmfe.compatibility import compute_compatibility
from datetime import datetime, timedelta

def run_actual_per_service():
    import random
    random.seed(42)
    requests = []
    base_time = datetime.now()
    for i in range(100):
        rt = random.choices(["ride", "food", "parcel"], weights=[0.4, 0.4, 0.2])[0]
        requests.append(SimulationRequest(
            id=i,
            request_type=rt,
            pickup_lat=11.01 + random.uniform(-0.05, 0.05),
            pickup_lng=77.01 + random.uniform(-0.05, 0.05),
            drop_lat=11.01 + random.uniform(-0.05, 0.05),
            drop_lng=77.01 + random.uniform(-0.05, 0.05),
            demand=1,
            priority="Medium",
            request_timestamp=base_time + timedelta(minutes=random.randint(0, 30))
        ))
        
    batched = set()
    total_types = {"ride": 0, "food": 0, "parcel": 0}
    for r in requests:
        total_types[r.request_type] += 1
        
    for i, r1 in enumerate(requests):
        for j, r2 in enumerate(requests):
            if i >= j: continue
            score, factors, details = compute_compatibility(r1, r2, adaptive_mode=False)
            if score >= 70.0 and details["capacity"]["v_ij"] > 0:
                batched.add(i)
                batched.add(j)
                
    batched_types = {"ride": 0, "food": 0, "parcel": 0}
    for i in batched:
        batched_types[requests[i].request_type] += 1
        
    for rt in ["ride", "food", "parcel"]:
        t = total_types[rt]
        b = batched_types[rt]
        p = (b/t*100) if t > 0 else 0
        print(f"{rt.capitalize()}: Total={t}, Batched={b}, Participation={p:.1f}%")

if __name__ == "__main__":
    run_actual_per_service()
