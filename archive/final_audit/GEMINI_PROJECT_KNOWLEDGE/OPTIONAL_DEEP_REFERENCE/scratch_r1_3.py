import sys
import os
import time
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

def test_workload(n: int, db: Session, exp: ExperimentDB, providers, vehicles):
    print(f"\n{'='*50}\nTesting N={n}\n{'='*50}")
    
    # 1. Generate requests
    db.query(SimulationRequest).delete()
    db.query(Trip).delete()
    from app.services.mock_adapters import generate_simulation_requests
    requests = generate_simulation_requests(count=n, db=db, request_types={"ride": 0.40, "food": 0.40, "parcel": 0.20})
    db.commit()
    
    # 2. Joint Optimization Baseline (Legacy)
    # We must reset statuses so AIOrchestrator picks them up
    for r in requests:
        r.status = "Pending"
    db.commit()
    
    from app.engine.optimizer import AIOrchestrator
    orchestrator = AIOrchestrator(providers=providers, vehicles=vehicles, db=db)
    
    t0 = time.perf_counter()
    legacy_results = orchestrator.run()
    legacy_time = time.perf_counter() - t0
    
    legacy_served = sum(r.get('request_count', 0) for r in legacy_results)
    legacy_dist = sum(r['best_route']['distance_km'] for r in legacy_results)
    
    print(f"--- Legacy Joint VRP ---")
    print(f"Time: {legacy_time:.2f}s")
    print(f"Served: {legacy_served}/{n}")
    print(f"Total distance: {legacy_dist:.2f} km")
    
    # 3. DMFE Pipeline
    db.query(SimulationRequest).delete()
    db.query(Trip).delete()
    requests = generate_simulation_requests(count=n, db=db, request_types={"ride": 0.40, "food": 0.40, "parcel": 0.20})
    db.commit()
    
    from app.dmfe.pipeline import PipelineRunner
    runner = PipelineRunner()
    
    t0 = time.perf_counter()
    dmfe_result = runner.run(db, limit=n)
    dmfe_time = time.perf_counter() - t0
    
    # Calculate DMFE metrics
    trip_ids = [d["trip_id"] for d in dmfe_result.dispatches]
    trips = db.query(Trip).filter(Trip.id.in_(trip_ids)).all() if trip_ids else []
    dmfe_dist = sum(t.total_distance_km for t in trips if t.total_distance_km)
    
    print(f"--- DMFE Pipeline ---")
    print(f"Time: {dmfe_time:.2f}s")
    print(f"Served: {dmfe_result.requests_processed}/{n}")
    print(f"Total distance: {dmfe_dist:.2f} km")


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
    
    providers = db.query(Provider).all()
    vehicles = db.query(Vehicle).all()
    
    test_workload(50, db, exp, providers, vehicles)
    test_workload(100, db, exp, providers, vehicles)
    test_workload(250, db, exp, providers, vehicles)


if __name__ == "__main__":
    main()
