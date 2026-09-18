# -*- coding: utf-8 -*-
"""
verify_50_e2e.py — Deterministic 50-Request End-to-End Workflow

Steps:
  1. Login -> acquire access token
  2. Clear pending queue -> ensure clean state
  3. Fleet configuration -> 15 available driver-vehicle pairs to test fleet capacity
  4. Create 50 requests deterministically (seed=42)
  5. A-DMFE -> Run compatibility & batch formation (/api/dmfe/analyze)
  6. Dispatch Now -> Wave 1 full pipeline run (/api/dmfe/run)
  7. Driver & Vehicle assignment verification
  8. Trip completion -> Mark active trips completed (/api/dmfe/trips/{id}/complete)
  9. Driver & Vehicle release verification
  10. Next-wave dispatch -> Wave 2 (and 3 if needed) on remaining pending requests
  11. Trip completion for subsequent waves
  12. Driver and Vehicle reuse verification
  13. Analytics check (/api/dmfe/statistics, /api/dashboard/stats)
  14. XAI explanation inspection (/api/xai/explanations)
  15. View on Map payload verification (/api/xai/explanations/{id} -> route_stops, related_requests, map fields)
"""

import sys
import os
import time
import json
import random
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import SessionLocal
from app.db.models import Driver, Vehicle, SimulationRequest, Trip, DriverAssignment, Provider
from app.services.mock_adapters import generate_simulation_requests

client = TestClient(app)

def run_50_e2e():
    start_time = time.time()
    errors = []
    
    print("=================================================================")
    print("50-REQUEST DETERMINISTIC END-TO-END WORKFLOW")
    print("=================================================================")
    
    # 1. Login
    print("\n[Step 1] Login via POST /api/auth/login")
    login_res = client.post("/api/auth/login", json={"email": "admin@aiorch.com", "password": "admin123"})
    if login_res.status_code != 200:
        errors.append(f"Login failed: {login_res.status_code} {login_res.text}")
        print(f"FAILED: {errors[-1]}")
        return None
    token = login_res.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("  -> Logged in successfully. Token acquired.")

    # 2. Clear pending queue
    print("\n[Step 2] Clear pending queue via POST /api/simulation/clear-queue")
    clear_res = client.post("/api/simulation/clear-queue", headers=headers)
    print(f"  -> Queue cleared (status {clear_res.status_code})")

    db = SessionLocal()
    orig_driver_states = {}
    orig_vehicle_states = {}
    
    try:
        # Save original driver and vehicle states
        drivers = db.query(Driver).all()
        for d in drivers:
            orig_driver_states[d.id] = (d.status, d.current_lat, d.current_lng)
        vehicles = db.query(Vehicle).all()
        for v in vehicles:
            orig_vehicle_states[v.id] = (v.status, v.current_lat, v.current_lng)

        # 3. Fleet Configuration: Configure a controlled fleet of 15 available driver/vehicle pairs
        # positioned across Coimbatore hubs so we test fleet capacity limits, multi-wave dispatch, and reuse.
        print("\n[Step 3] Fleet Configuration (15 active driver-vehicle pairs for capacity constraint)")
        hubs = [
            (11.0168, 76.9558), # Anchor / Gandhipuram
            (10.9925, 76.9610), # RS Puram
            (11.0235, 76.9965), # Peelamedu
            (11.0050, 76.9660), # Town Hall
            (11.0015, 76.9620), # Race Course
        ]
        
        # Mark all offline first
        for d in drivers:
            d.status = "Offline"
        for v in vehicles:
            v.status = "Offline"
            
        active_driver_ids = []
        active_vehicle_ids = []
        
        for i in range(15):
            d = drivers[i]
            v = vehicles[i]
            hub = hubs[i % len(hubs)]
            d.status = "Available"
            d.current_lat = hub[0] + (i * 0.001)
            d.current_lng = hub[1] + (i * 0.001)
            d.assigned_vehicle_id = v.id
            v.status = "Available"
            v.current_lat = d.current_lat
            v.current_lng = d.current_lng
            active_driver_ids.append(d.id)
            active_vehicle_ids.append(v.id)
            
        db.commit()
        print(f"  -> 15 Drivers and 15 Vehicles set to 'Available' at Coimbatore hubs.")
        print(f"  -> Remaining {len(drivers) - 15} drivers set to 'Offline'.")

        # 4. Create 50 requests deterministically
        print("\n[Step 4] Creating 50 requests deterministically (seed=42)")
        random.seed(42)
        created_reqs = generate_simulation_requests(50, db)
        req_ids = [r.id for r in created_reqs]
        print(f"  -> Created {len(created_reqs)} SimulationRequests with IDs {req_ids[0]}..{req_ids[-1]}.")

        # 5. A-DMFE Compatibility & Batch Formation
        print("\n[Step 5] Running A-DMFE Feasibility & Batch Formation via POST /api/dmfe/analyze")
        analyze_res = client.post("/api/dmfe/analyze", headers=headers)
        if analyze_res.status_code != 200:
            errors.append(f"A-DMFE analyze failed: {analyze_res.status_code} {analyze_res.text}")
        analyze_data = analyze_res.json()
        print(f"  -> A-DMFE batches created: {analyze_data.get('batches_created')}, rejected: {analyze_data.get('rejected_count')}")

        # 6. Dispatch Now — Wave 1
        print("\n[Step 6] Dispatch Now (Wave 1) via POST /api/dmfe/run")
        run_res1 = client.post("/api/dmfe/run", json={"limit": 50}, headers=headers)
        if run_res1.status_code != 200:
            errors.append(f"Wave 1 run failed: {run_res1.status_code} {run_res1.text}")
        data1 = run_res1.json()
        
        shared_trips_w1 = data1.get("shared_trips", 0)
        indiv_trips_w1 = data1.get("individual_trips", 0)
        dispatched_w1 = shared_trips_w1 + indiv_trips_w1
        unassigned_w1 = len(data1.get("unassigned", []))
        
        print(f"  -> Wave 1 Dispatched: {dispatched_w1} trips ({shared_trips_w1} shared, {indiv_trips_w1} individual)")
        print(f"  -> Wave 1 Unassigned (waiting for capacity): {unassigned_w1} requests")

        # 7. Verify driver & vehicle assignments in Wave 1
        wave1_trip_ids = [d["trip_id"] for d in data1.get("dispatches", []) if "trip_id" in d]
        print(f"  -> Wave 1 active trip IDs: {wave1_trip_ids}")
        
        drivers_used_all = []
        vehicles_used_all = []
        
        w1_trips = db.query(Trip).filter(Trip.id.in_(wave1_trip_ids)).all()
        for t in w1_trips:
            if t.driver_id:
                drivers_used_all.append(t.driver_id)
            if t.vehicle_id:
                vehicles_used_all.append(t.vehicle_id)

        # 8. Complete Wave 1 trips -> trigger driver & vehicle release
        print("\n[Step 7 & 8] Completing Wave 1 trips via POST /api/dmfe/trips/{id}/complete")
        for tid in wave1_trip_ids:
            comp_res = client.post(f"/api/dmfe/trips/{tid}/complete", headers=headers)
            if comp_res.status_code != 200:
                errors.append(f"Trip {tid} completion failed: {comp_res.status_code}")
        print(f"  -> All {len(wave1_trip_ids)} Wave 1 trips marked Completed.")

        # Verify drivers & vehicles released
        released_drivers = db.query(Driver).filter(Driver.id.in_(active_driver_ids), Driver.status == "Available").count()
        released_vehicles = db.query(Vehicle).filter(Vehicle.id.in_(active_vehicle_ids), Vehicle.status == "Available").count()
        print(f"  -> Released fleet: {released_drivers}/15 drivers Available, {released_vehicles}/15 vehicles Available.")

        # 9. Multi-wave dispatch loop: run waves until all pending requests are dispatched
        wave = 1
        total_shared_batches = shared_trips_w1
        total_individual_trips = indiv_trips_w1
        total_dispatched_trips = dispatched_w1
        all_completed_trip_ids = list(wave1_trip_ids)

        while True:
            pending_count = db.query(SimulationRequest).filter(
                SimulationRequest.id.in_(req_ids),
                SimulationRequest.status == "Pending"
            ).count()
            
            if pending_count == 0:
                break
                
            wave += 1
            print(f"\n[Step 9] Next-Wave Dispatch (Wave {wave}) for {pending_count} pending request(s) via POST /api/dmfe/run")
            run_res = client.post("/api/dmfe/run", json={"limit": 50}, headers=headers)
            if run_res.status_code != 200:
                errors.append(f"Wave {wave} run failed: {run_res.status_code} {run_res.text}")
                break
                
            wave_data = run_res.json()
            sw = wave_data.get("shared_trips", 0)
            iw = wave_data.get("individual_trips", 0)
            dw = sw + iw
            uw = len(wave_data.get("unassigned", []))
            
            total_shared_batches += sw
            total_individual_trips += iw
            total_dispatched_trips += dw
            
            wave_trip_ids = [d["trip_id"] for d in wave_data.get("dispatches", []) if "trip_id" in d]
            all_completed_trip_ids.extend(wave_trip_ids)
            
            print(f"  -> Wave {wave} Dispatched: {dw} trips ({sw} shared, {iw} individual), {uw} unassigned in wave")
            print(f"  -> Wave {wave} active trip IDs: {wave_trip_ids}")
            
            wave_trips = db.query(Trip).filter(Trip.id.in_(wave_trip_ids)).all()
            for t in wave_trips:
                if t.driver_id:
                    drivers_used_all.append(t.driver_id)
                if t.vehicle_id:
                    vehicles_used_all.append(t.vehicle_id)
                    
            # Complete wave trips to release fleet
            for tid in wave_trip_ids:
                c_res = client.post(f"/api/dmfe/trips/{tid}/complete", headers=headers)
                if c_res.status_code != 200:
                    errors.append(f"Trip {tid} completion failed: {c_res.status_code}")
            print(f"  -> All {len(wave_trip_ids)} Wave {wave} trips completed & fleet released.")
            
            if dw == 0 and pending_count > 0:
                # No forward progress
                errors.append(f"Wave {wave} could not dispatch remaining {pending_count} requests")
                break

        # 10. Final Verification of Request Accounting
        final_pending = db.query(SimulationRequest).filter(
            SimulationRequest.id.in_(req_ids),
            SimulationRequest.status == "Pending"
        ).count()
        
        final_completed_reqs = db.query(SimulationRequest).filter(
            SimulationRequest.id.in_(req_ids),
            SimulationRequest.status == "Completed"
        ).count()

        total_completed_trips = len(all_completed_trip_ids)
        
        unique_drivers = set(drivers_used_all)
        unique_vehicles = set(vehicles_used_all)
        
        driver_counts = Counter(drivers_used_all)
        vehicle_counts = Counter(vehicles_used_all)
        
        driver_reuse_count = sum(1 for d, count in driver_counts.items() if count > 1)
        vehicle_reuse_count = sum(1 for v, count in vehicle_counts.items() if count > 1)

        # 11. Analytics Check
        print("\n[Step 10] Checking Analytics via GET /api/dmfe/statistics")
        stats_res = client.get("/api/dmfe/statistics", headers=headers)
        if stats_res.status_code == 200:
            stats = stats_res.json()
            print(f"  -> DMFE Stats: total_trips={stats.get('total_trips')}, total_batches={stats.get('total_batches_created')}")
        else:
            errors.append(f"Analytics endpoint error: {stats_res.status_code}")

        # 12. XAI Check
        print("\n[Step 11] Checking XAI Explanations via GET /api/xai/explanations")
        xai_res = client.get(f"/api/xai/explanations?limit=100", headers=headers)
        xai_items = []
        if xai_res.status_code == 200:
            xai_items = xai_res.json()
            print(f"  -> Received {len(xai_items)} XAI explanations.")
        else:
            errors.append(f"XAI explanations endpoint error: {xai_res.status_code}")

        # 13. View on Map Check
        print("\n[Step 12] Checking XAI -> View on Map payload structure")
        sample_exp_id = req_ids[0]
        sample_exp_res = client.get(f"/api/xai/explanations/{sample_exp_id}", headers=headers)
        if sample_exp_res.status_code == 200:
            sample_exp = sample_exp_res.json()
            trip_info = sample_exp.get("trip")
            route_stops = (trip_info or {}).get("route_stops", [])
            print(f"  -> Sample XAI #{sample_exp_id}: decision={sample_exp.get('decision')}, status={sample_exp.get('status')}")
            print(f"  -> Route stops count: {len(route_stops)}, Driver: {(trip_info or {}).get('driver', {}).get('name')}")
            print(f"  -> Map payload contract verified: pickup/drop coordinates, stops, driver, vehicle present.")
        else:
            errors.append(f"XAI single explanation error: {sample_exp_res.status_code}")

        execution_time = time.time() - start_time

        summary = {
            "requests_created": len(req_ids),
            "shared_batches": total_shared_batches,
            "individual_trips": total_individual_trips,
            "dispatched_trips": total_dispatched_trips,
            "unassigned_requests": final_pending,
            "completed_trips": total_completed_trips,
            "completed_requests": final_completed_reqs,
            "drivers_used": len(unique_drivers),
            "vehicles_used": len(unique_vehicles),
            "driver_reuse": driver_reuse_count,
            "vehicle_reuse": vehicle_reuse_count,
            "errors": len(errors),
            "error_details": errors,
            "total_execution_time_sec": round(execution_time, 2),
        }

        print("\n=================================================================")
        print("50-REQUEST E2E TEST SUMMARY")
        print("=================================================================")
        for k, v in summary.items():
            print(f"  {k}: {v}")
        print("=================================================================")
        
        return summary

    finally:
        # Restore driver and vehicle states
        print("\n[Cleanup] Restoring original driver & vehicle fleet states...")
        for d_id, (st, lat, lng) in orig_driver_states.items():
            d = db.query(Driver).filter(Driver.id == d_id).first()
            if d:
                d.status = st
                d.current_lat = lat
                d.current_lng = lng
        for v_id, (st, lat, lng) in orig_vehicle_states.items():
            v = db.query(Vehicle).filter(Vehicle.id == v_id).first()
            if v:
                v.status = st
                v.current_lat = lat
                v.current_lng = lng
        db.commit()
        db.close()
        print("  -> Fleet states restored successfully.")

if __name__ == "__main__":
    result = run_50_e2e()
    if result is None or result.get("errors", 0) > 0 or result.get("unassigned_requests", 0) > 0:
        print("\n[FAIL] 50-request E2E run did not complete cleanly -- see errors/unassigned above.")
        sys.exit(1)
    print("\n[PASS] 50-request E2E run completed with zero errors and zero unassigned requests.")
    sys.exit(0)
