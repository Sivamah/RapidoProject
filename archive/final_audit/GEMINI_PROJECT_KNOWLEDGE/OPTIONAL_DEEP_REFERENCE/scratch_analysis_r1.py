import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

import asyncio
from datetime import datetime, timedelta
from app.db.models import SimulationRequest, Driver
from app.dmfe.pipeline import DMFE, DispatchConfig

class RequestType:
    RIDE = "ride"
    FOOD = "food"
    PARCEL = "parcel"
    
def setup_synthetic_pool(n_req):
    requests = []
    base_time = datetime.now()
    import random
    random.seed(42) # Use a fixed seed for reproducible synthetic workload
    
    for i in range(n_req):
        rt = random.choices(
            [RequestType.RIDE, RequestType.FOOD, RequestType.PARCEL],
            weights=[0.4, 0.4, 0.2]
        )[0]
        
        req = SimulationRequest(
            id=f"req_{i}",
            request_type=rt,
            pickup_lat=11.01 + random.uniform(-0.05, 0.05),
            pickup_lng=77.01 + random.uniform(-0.05, 0.05),
            drop_lat=11.01 + random.uniform(-0.05, 0.05),
            drop_lng=77.01 + random.uniform(-0.05, 0.05),
            pickup_address="",
            drop_address="",
            demand=1,
            priority="Medium",
            weight_kg=0.0,
            vehicle_type="Auto",
            estimated_distance_km=0.0,
            status="Pending",
            max_acceptable_delay_min=20.0,
            sharing_preference="Any",
            request_timestamp=base_time + timedelta(minutes=random.randint(0, 30))
        )
        requests.append(req)
        
    drivers = []
    for i in range(60):
        d = Driver(
            id=f"drv_{i}",
            name="Driver",
            status="Available",
            current_lat=11.01 + random.uniform(-0.05, 0.05),
            current_lng=77.01 + random.uniform(-0.05, 0.05),
            mixed_service_willingness=1.0
        )
        drivers.append(d)
        
    return requests, drivers

async def test_per_service():
    print("=== Per Service Evaluation (N=100) ===")
    requests, drivers = setup_synthetic_pool(100)
    config = DispatchConfig(use_haversine=True, adaptive_mode=False)
    pipeline = DMFE(config)
    pipeline.drivers = drivers
    
    # Process requests
    start = time.time()
    await pipeline.process_pool(requests)
    print(f"DMFE Pipeline time: {time.time() - start:.2f}s")
    
    types = [RequestType.RIDE, RequestType.FOOD, RequestType.PARCEL]
    total_by_type = {rt: 0 for rt in types}
    batched_by_type = {rt: 0 for rt in types}
    
    for r in requests:
        total_by_type[r.request_type] += 1
        
    for trip in pipeline.completed_trips:
        if len(trip.request_ids) > 1:
            for rid in trip.request_ids:
                req = next(r for r in requests if r.id == rid)
                batched_by_type[req.request_type] += 1
                
    for rt in types:
        t = total_by_type[rt]
        b = batched_by_type[rt]
        p = (b/t*100) if t > 0 else 0
        print(f"{rt}: Total={t}, Batched={b}, Participation={p:.1f}%")

if __name__ == "__main__":
    asyncio.run(test_per_service())
