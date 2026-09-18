# -*- coding: utf-8 -*-
"""
verify_xai_map.py — demonstrate the XAI → live-map link.

Seeds the curated demo scenario, runs the real DMFE pipeline, then prints
the XAI payloads the frontend map consumes for one ACCEPTED batch and one
REJECTED request:

    * accepted  — decision "Compatible for Batching" whose request was
                  dispatched in a shared Trip (route stops + driver/vehicle)
    * rejected  — decision "Standalone Direct Routing" rejected from
                  batching (the real rejection reason, partner highlighted)

Usage:  backend\\.venv\\Scripts\\python.exe backend\\scripts\\verify_xai_map.py
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app

DEMO_TAG = "[A-DMFE Demo Scenario]"
client = TestClient(app)


def login():
    r = client.post("/api/auth/login", json={"email": "admin@aiorch.com", "password": "admin123"})
    if r.status_code != 200:
        print(f"Login failed: {r.status_code} {r.text}")
        sys.exit(1)
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


def summary(exp):
    """What the map layer needs from one explanation, as in the frontend."""
    trip = exp.get("trip")
    return {
        "request_id": exp["request_id"],
        "request_type": exp["request_type"],
        "decision": exp["decision"],
        "status": exp["status"],
        "reason": exp["reason"],
        "compatibility_score": exp.get("factors", {}).get("overall_compatibility_score"),
        "partner_ids": exp.get("batched_with_request_ids", []),
        "related_requests": [
            {
                "request_id": p["request_id"],
                "relation": ("self" if p["request_id"] == exp["request_id"]
                             else ("partner" if p["request_id"] in exp.get("batched_with_request_ids", [])
                                   else "trip")),
                "pickup": (p["pickup_lat"], p["pickup_lng"]),
                "drop": (p["drop_lat"], p["drop_lng"]),
            }
            for p in exp.get("related_requests", [])
        ],
        "route_stops": [
            {"request_id": s["request_id"], "action": s["action"],
             "lat": round(s["lat"], 6), "lng": round(s["lng"], 6),
             "arrival_min": s["arrival_min"]}
            for s in (trip or {}).get("route_stops", [])
        ],
        "driver": (trip or {}).get("driver"),
        "vehicle": (trip or {}).get("vehicle"),
        "trip_code": (trip or {}).get("trip_code"),
        "is_shared": (trip or {}).get("is_shared"),
    }


def pick_accepted(exps):
    # Prefer a demo request dispatched in a shared trip (full route present).
    for e in exps:
        if e.get("decision") == "Compatible for Batching" and e.get("trip") \
                and DEMO_TAG in (e.get("pickup_address") or ""):
            n = summary(e)
            if n["route_stops"]:
                return e, n
    for e in exps:
        if e.get("decision") == "Compatible for Batching" and e.get("trip"):
            n = summary(e)
            if n["route_stops"]:
                return e, n
    return None, None


def pick_rejected(exps):
    # 1) demo request rejected from batching (best demo: partner highlighted)
    for e in exps:
        if e.get("status") == "Incompatible" \
                and e.get("decision") == "Standalone Direct Routing" \
                and "Rejected from batching" in (e.get("reason") or "") \
                and DEMO_TAG in (e.get("pickup_address") or ""):
            return e, summary(e)
    # 2) any request rejected from batching
    for e in exps:
        if e.get("status") == "Incompatible" \
                and e.get("decision") == "Standalone Direct Routing" \
                and "Rejected from batching" in (e.get("reason") or ""):
            return e, summary(e)
    # 3) fallback: any standalone demo request
    for e in exps:
        if e.get("status") == "Incompatible" \
                and e.get("decision") == "Standalone Direct Routing" \
                and DEMO_TAG in (e.get("pickup_address") or ""):
            return e, summary(e)
    return None, None


def main():
    headers = login()

    print("== Seeding demo scenario ==")
    r = client.post("/api/dmfe/demo/seed", headers=headers)
    print(f"seed -> {r.status_code} {r.text[:160]}")

    print("\n== Running DMFE pipeline on the pending queue ==")
    r = client.post("/api/dmfe/run", json={"limit": 200}, headers=headers)
    if r.status_code != 200:
        print(f"run failed: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    run = r.json()
    print(f"dispatch -> assigned {len(run.get('assigned', []))}, "
          f"unassigned {len(run.get('unassigned', []))}")

    print("\n== Fetching XAI explanations ==")
    exps = client.get("/api/xai/explanations?limit=400", headers=headers).json()
    print(f"{len(exps)} explanations returned")

    accepted, accepted_summary = pick_accepted(exps)
    rejected, rejected_summary = pick_rejected(exps)

    print("\n" + "=" * 80)
    print("ACCEPTED BATCH -> live map payload")
    print("=" * 80)
    if accepted:
        print(json.dumps(accepted_summary, indent=2, ensure_ascii=False))
    else:
        print("No 'Compatible for Batching' explanation with a dispatched trip found.")

    print("\n" + "=" * 80)
    print("REJECTED REQUEST -> live map payload")
    print("=" * 80)
    if rejected:
        print(json.dumps(rejected_summary, indent=2, ensure_ascii=False))
    else:
        print("No Standalone/Incompatible explanation found.")

    print("\nVerification complete."
          + ("  (map focus URL: /live-map?xai=%d)" % accepted["request_id"] if accepted else ""))

    client.close()


if __name__ == "__main__":
    main()