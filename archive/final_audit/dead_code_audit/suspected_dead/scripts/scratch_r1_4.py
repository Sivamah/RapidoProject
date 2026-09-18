import sys
import os
import random

# Add backend to path
backend_dir = os.path.abspath(r"d:\rapidoproject\backend")
sys.path.insert(0, backend_dir)

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app.db.database import Base
from app.db.models import Provider, Vehicle, SimulationRequest, Trip

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GOOGLE_MAPS_API_KEY"] = ""

from evaluation.framework import ExperimentDB, SYSTEM_CONFIG

def main():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    from app.db.database import SessionLocal
    db = SessionLocal()
    
    exp = ExperimentDB()
    exp.reset_schema()
    rng = random.Random(1050)
    exp.seed_system_config_with(db, SYSTEM_CONFIG)
    exp.seed_fleet(db, rng)
    
    # 1. Generate requests
    from app.services.mock_adapters import generate_simulation_requests
    requests = generate_simulation_requests(count=100, db=db, request_types={"ride": 0.40, "food": 0.40, "parcel": 0.20})
    db.commit()
    
    # 2. Run DMFE Pipeline
    from app.dmfe.pipeline import PipelineRunner
    runner = PipelineRunner()
    result = runner.run(db, limit=100)
    
    # 3. Calculate Per-Service metrics
    trip_ids = [d["trip_id"] for d in result.dispatches]
    trips = db.query(Trip).filter(Trip.id.in_(trip_ids)).all() if trip_ids else []
    
    # Map trip ID to trip object for easy lookup
    trip_map = {t.id: t for t in trips}
    
    stats = {
        "ride": {"total": 0, "batched": 0},
        "food": {"total": 0, "batched": 0},
        "parcel": {"total": 0, "batched": 0}
    }
    
    # We look at all assigned requests in the database
    assigned_requests = db.query(SimulationRequest).filter(SimulationRequest.status.in_(["Assigned", "Completed"])).all()
    
    # To find out if a request is batched, we check if it's part of a shared trip.
    # The pipeline records trip_id on the assignment, but SimulationRequest doesn't have trip_id directly in the model.
    # Wait, how does SimulationRequest link to Trip?
    # Trip has request_ids_json = [1, 2, ...]
    import json
    for t in trips:
        req_ids = json.loads(t.request_ids_json)
        is_shared = t.is_shared
        for rid in req_ids:
            req = db.query(SimulationRequest).filter(SimulationRequest.id == rid).first()
            if req and req.request_type in stats:
                stats[req.request_type]["total"] += 1
                if is_shared:
                    stats[req.request_type]["batched"] += 1

    print("=== PER-SERVICE RESULTS PILOT ===")
    for svc, s in stats.items():
        participation = (s["batched"] / s["total"] * 100) if s["total"] > 0 else 0
        print(f"{svc.capitalize()}:")
        print(f"  Total: {s['total']}")
        print(f"  Batched: {s['batched']}")
        print(f"  Participation: {participation:.1f}%\n")


if __name__ == "__main__":
    main()
