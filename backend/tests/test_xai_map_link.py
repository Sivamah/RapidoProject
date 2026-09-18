"""
XAI → live-map linking tests.

These verify the additive payload enrichment the live map consumes:

  * pickup/drop coordinates on every explanation
  * `related_requests` — the request itself, its XAI-evaluated partner, and
    the real dispatched-trip members (deduped), each with coords
  * the `trip` link — driver, vehicle, and ordered route stops with coords
  * a deterministic non-dispatched ("rejected from batching"-style) case

No A-DMFE scoring, batching, or decision logic is exercised or changed.
"""

from __future__ import annotations

import json

from app.dmfe.compatibility import CompatibilityCalculator
from app.services.xai_service import _generate_explanation_for_request


def _explain(db, req, compute_kwargs=None, trip_by_request=None):
    return _generate_explanation_for_request(
        db,
        CompatibilityCalculator(),
        req,
        "Test Provider",
        60.0,
        compute_kwargs,
        trip_by_request,
    )


def test_dispatched_shared_trip_carries_map_link_payload(
    db, make_request, make_driver, make_vehicle, make_trip
):
    r1 = make_request(
        request_type="ride",
        pickup_address="GANGA",
        drop_address="HOPE",
        pickup_lat=11.0168, pickup_lng=76.9558,
        drop_lat=11.0200, drop_lng=76.9700,
    )
    r2 = make_request(
        request_type="ride",
        pickup_address="STAND",
        drop_address="STAD",
        pickup_lat=11.0200, pickup_lng=76.9700,
        drop_lat=11.0350, drop_lng=76.9850,
    )
    driver = make_driver(name="Driver Kumar", current_lat=11.01, current_lng=76.96)
    vehicle = make_vehicle(name="Vehicle-1", vehicle_type="Car", current_lat=11.02, current_lng=76.97)
    trip = make_trip(
        requests=[r1, r2],
        driver_id=driver.id,
        vehicle_id=vehicle.id,
        is_shared=True,
        status="Active",
        stop_order_json=json.dumps([
            {"request_id": r1.id, "action": "pickup", "arrival_min": 0.0},
            {"request_id": r2.id, "action": "pickup", "arrival_min": 6.0},
            {"request_id": r1.id, "action": "drop", "arrival_min": 12.0},
            {"request_id": r2.id, "action": "drop", "arrival_min": 18.0},
        ]),
    )

    exp = _explain(db, r1)

    assert exp.pickup_lat == r1.pickup_lat
    assert exp.pickup_lng == r1.pickup_lng
    assert exp.drop_lat == r1.drop_lat
    assert exp.drop_lng == r1.drop_lng

    # related_requests: self first, then partner + trip members (deduped)
    assert [p.request_id for p in exp.related_requests] == [r1.id, r2.id]
    for p in exp.related_requests:
        assert (p.pickup_lat, p.pickup_lng) != (0.0, 0.0)

    assert exp.trip is not None
    assert exp.trip.trip_id == trip.id
    assert exp.trip.trip_code == trip.trip_code
    assert exp.trip.is_shared is True
    assert exp.trip.driver is not None
    assert exp.trip.driver.name == "Driver Kumar"
    assert exp.trip.vehicle is not None
    assert exp.trip.vehicle.name == "Vehicle-1"
    assert exp.trip.vehicle.vehicle_type == "Car"

    # route polyline: one vertex per stop, coords reconstructed from requests
    assert [s.request_id for s in exp.trip.route_stops] == [r1.id, r2.id, r1.id, r2.id]
    assert [s.action for s in exp.trip.route_stops] == ["pickup", "pickup", "drop", "drop"]
    assert exp.trip.route_stops[0].lat == r1.pickup_lat
    assert exp.trip.route_stops[2].lat == r1.drop_lat
    assert exp.trip.route_stops[3].lng == r2.drop_lng

    assert exp.key_reasons
    assert exp.reason


def test_standalone_request_has_coords_and_no_trip(
    db, make_request
):
    req = make_request(
        request_type="parcel",
        pickup_address="AIRPORT",
        drop_address="RAIL",
        pickup_lat=11.0300, pickup_lng=76.9600,
        drop_lat=11.0400, drop_lng=76.9900,
    )

    exp = _explain(db, req)

    assert exp.decision == "Standalone Direct Routing"
    assert exp.status == "Incompatible"
    assert exp.pickup_lat == req.pickup_lat
    assert exp.drop_lng == req.drop_lng
    assert exp.trip is None
    assert [p.request_id for p in exp.related_requests] == [req.id]
    assert exp.key_reasons
    assert exp.reason