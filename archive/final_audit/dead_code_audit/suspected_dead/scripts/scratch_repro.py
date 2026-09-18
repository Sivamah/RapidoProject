import sys
import os
import random

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

def run_pipeline(db, seed, limit=50):
    random.seed(seed)
    exp = ExperimentDB()
    exp.reset_schema()
    rng = random.Random(seed)
    exp.seed_system_config_with(db, SYSTEM_CONFIG)
    exp.seed_fleet(db, rng)
    
    from app.services.mock_adapters import generate_simulation_requests
    generate_simulation_requests(count=limit, db=db, request_types={"ride": 0.40, "food": 0.40, "parcel": 0.20})
    db.commit()
    
    from app.dmfe.pipeline import PipelineRunner
    runner = PipelineRunner()
    result = runner.run(db, limit=limit)
    
    trip_ids = [d["trip_id"] for d in result.dispatches]
    trips = db.query(Trip).filter(Trip.id.in_(trip_ids)).all() if trip_ids else []
    dist = sum(t.total_distance_km for t in trips if t.total_distance_km)
    
    return {
        "processed": result.requests_processed,
        "shared": result.shared_trips,
        "individual": result.individual_trips,
        "assignments": result.assignments_created,
        "unassigned": len(result.unassigned),
        "distance": dist
    }

def main():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    from app.db.database import SessionLocal
    
    db1 = SessionLocal()
    out1 = run_pipeline(db1, seed=1234, limit=50)
    db1.close()
    
    # Needs a fresh DB schema to run again safely in memory
    engine2 = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine2)
    SessionLocal2 = type(SessionLocal)(bind=engine2)
    db2 = SessionLocal2()
    
    out2 = run_pipeline(db2, seed=1234, limit=50)
    db2.close()
    
    print(f"Run 1: {out1}")
    print(f"Run 2: {out2}")
    
    if out1 == out2:
        print("Outputs are strictly IDENTICAL.")
    else:
        print("Outputs DIFFER!")

if __name__ == "__main__":
    main()
