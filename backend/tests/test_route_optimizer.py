# -*- coding: utf-8 -*-
"""
RouteOptimizer (OR-Tools PDP solver) coverage — Finding 7 of the reliability
audit (docs/reports/TARGETED_FINDINGS_VERIFICATION.md): `backend/app/dmfe/
optimizer.py` had zero direct pytest coverage, confirmed via exhaustive grep
for `RouteOptimizer`, `optimize_trip`, `_solve_pdp` across every existing
test file. It is the single largest untested module in the DMFE core, and is
called from the live dispatch path in `driver_selection.py`.

These tests exercise both code paths:
  - the single-request fast path (`_build_single_route`, which deliberately
    bypasses OR-Tools entirely — see its own docstring),
  - the real OR-Tools solve for 2+ requests (`_solve_pdp` / `_build_route`).

For the solver path we assert structural / PDP invariants (pickup visited
before its own delivery, every request represented exactly once, capacity
respected) rather than exact routes or distances, since OR-Tools' local
search is only required to return a FEASIBLE solution, not a byte-identical
one across runs, solver versions, or machines. This mirrors the existing
invariant-style tests in `test_pipeline_accounting.py`.

The shared-trip coordinates below intentionally reuse the exact pair spacing
already proven to solve in this repo's own `test_pipeline_accounting.py`
(anchor-relative offsets of ~0.001 degrees, i.e. driver_selection.py's own
live dispatch path already exercises this magnitude successfully), rather
than inventing new, unverified distances.
"""

from __future__ import annotations

import pytest

from app.dmfe.compatibility import clear_config_cache
from app.dmfe.optimizer import OptimizedRoute, RouteOptimizer

ANCHOR_LAT, ANCHOR_LNG = 11.0168, 76.9558


@pytest.fixture(autouse=True)
def _fresh_config_cache():
    """The SystemConfig TTL cache (VRP rules included) is module-level."""
    clear_config_cache()
    yield
    clear_config_cache()


@pytest.fixture()
def optimizer():
    return RouteOptimizer()


def _driver_and_vehicle(make_driver, make_vehicle, capacity=4):
    v = make_vehicle(capacity=capacity, current_lat=ANCHOR_LAT, current_lng=ANCHOR_LNG)
    d = make_driver(current_lat=ANCHOR_LAT, current_lng=ANCHOR_LNG, assigned_vehicle_id=v.id)
    return d, v


# ── Single-request fast path ────────────────────────────────────────────────

def test_single_request_route_is_depot_pickup_drop(
    db, make_request, make_driver, make_vehicle, optimizer
):
    d, v = _driver_and_vehicle(make_driver, make_vehicle)
    req = make_request(
        pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
        drop_lat=11.02, drop_lng=76.97,
        demand=1,
    )
    db.commit()

    route = optimizer.optimize_trip(
        db, requests=[req], vehicle=v, driver=d, trip_key="TRIP-TEST"
    )

    assert isinstance(route, OptimizedRoute)
    assert route.request_ids == [req.id]
    assert route.is_shared is False
    assert route.vehicle_id == v.id
    assert route.driver_id == d.id
    assert len(route.stop_order) == 2
    assert route.stop_order[0].action == "pickup"
    assert route.stop_order[1].action == "drop"
    assert route.total_distance_km > 0
    # No GOOGLE_MAPS_API_KEY is configured in the test environment.
    assert route.matrix_source == "haversine_fallback"


def test_single_request_utilization_reflects_demand_over_capacity(
    db, make_request, make_driver, make_vehicle, optimizer
):
    d, v = _driver_and_vehicle(make_driver, make_vehicle, capacity=4)
    req = make_request(
        pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
        drop_lat=11.02, drop_lng=76.97,
        demand=2,
    )
    db.commit()

    route = optimizer.optimize_trip(db, requests=[req], vehicle=v, driver=d)

    assert route.utilization_pct == 50.0  # 2 / 4 * 100


def test_to_dict_contract(db, make_request, make_driver, make_vehicle, optimizer):
    """OptimizedRoute.to_dict() is consumed by the dashboards — pin its shape."""
    d, v = _driver_and_vehicle(make_driver, make_vehicle)
    req = make_request(
        pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
        drop_lat=11.02, drop_lng=76.97,
    )
    db.commit()

    route = optimizer.optimize_trip(db, requests=[req], vehicle=v, driver=d)
    d_dict = route.to_dict()

    assert d_dict["request_ids"] == [req.id]
    assert d_dict["driver_id"] == d.id
    assert d_dict["vehicle_id"] == v.id
    assert len(d_dict["best_route"]["stops"]) == len(route.stop_order)
    assert d_dict["is_batched"] is False
    assert "optimization_score" in d_dict
    assert "fuel_saved_l" in d_dict


# ── Weight / capacity gates ─────────────────────────────────────────────────

def test_combined_weight_over_limit_raises(
    db, make_request, make_driver, make_vehicle, optimizer, set_config
):
    set_config("max_weight_kg", 10.0)
    db.commit()
    clear_config_cache()

    d, v = _driver_and_vehicle(make_driver, make_vehicle)
    req = make_request(
        pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
        drop_lat=11.02, drop_lng=76.97,
        weight_kg=50.0,
    )
    db.commit()

    with pytest.raises(ValueError, match="exceeds"):
        optimizer.optimize_trip(db, requests=[req], vehicle=v, driver=d)


def test_combined_demand_over_capacity_raises(
    db, make_request, make_driver, make_vehicle, optimizer
):
    d, v = _driver_and_vehicle(make_driver, make_vehicle, capacity=1)
    req = make_request(
        pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
        drop_lat=11.02, drop_lng=76.97,
        demand=5,
    )
    db.commit()

    with pytest.raises(ValueError, match="capacity"):
        optimizer.optimize_trip(db, requests=[req], vehicle=v, driver=d)


def test_optimize_trip_requires_at_least_one_request(db, optimizer):
    with pytest.raises(ValueError):
        optimizer.optimize_trip(db, requests=[])


# ── Shared trip via the real OR-Tools solver ────────────────────────────────

def _shared_pair(make_request):
    """Two requests at the exact offsets already proven to solve feasibly in
    this repo's own test_pipeline_accounting.py (via the live dispatch path,
    driver_selection.py -> route_optimizer.optimize_trip)."""
    r1 = make_request(
        priority="Medium",
        pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
        drop_lat=11.02, drop_lng=76.97,
        demand=1,
    )
    r2 = make_request(
        priority="Medium",
        pickup_lat=ANCHOR_LAT + 0.001, pickup_lng=ANCHOR_LNG,
        drop_lat=11.021, drop_lng=76.971,
        demand=1,
    )
    return r1, r2


def test_shared_trip_respects_pickup_before_delivery(
    db, make_request, make_driver, make_vehicle, optimizer
):
    """
    PDP hard constraint (AddPickupAndDelivery + VehicleVar equality in
    _solve_pdp): every request's pickup must be visited before its own drop.
    This is a structural invariant OR-Tools guarantees for ANY feasible
    solution, so it holds regardless of solver nondeterminism.
    """
    d, v = _driver_and_vehicle(make_driver, make_vehicle, capacity=4)
    r1, r2 = _shared_pair(make_request)
    db.commit()

    route = optimizer.optimize_trip(
        db, requests=[r1, r2], vehicle=v, driver=d, trip_key="BATCH-TEST"
    )

    assert route.is_shared is True
    assert set(route.request_ids) == {r1.id, r2.id}
    assert len(route.stop_order) == 4

    pickup_idx, drop_idx = {}, {}
    for i, s in enumerate(route.stop_order):
        (pickup_idx if s.action == "pickup" else drop_idx)[s.request_id] = i

    for rid in (r1.id, r2.id):
        assert rid in pickup_idx and rid in drop_idx, (
            f"request {rid} missing a pickup or drop stop: {route.stop_order}"
        )
        assert pickup_idx[rid] < drop_idx[rid], (
            f"request {rid} dropped before it was picked up: "
            f"pickup@{pickup_idx[rid]} drop@{drop_idx[rid]}"
        )


def test_shared_trip_every_request_visited_exactly_once(
    db, make_request, make_driver, make_vehicle, optimizer
):
    d, v = _driver_and_vehicle(make_driver, make_vehicle, capacity=4)
    r1, r2 = _shared_pair(make_request)
    db.commit()

    route = optimizer.optimize_trip(db, requests=[r1, r2], vehicle=v, driver=d)

    seen = [s.request_id for s in route.stop_order]
    for rid in (r1.id, r2.id):
        # Exactly one pickup + one drop each — no duplicate or missing stops.
        assert seen.count(rid) == 2


# ── optimize_batch ───────────────────────────────────────────────────────────

def test_optimize_batch_resolves_requests_from_batch(
    db, make_request, make_batch, make_driver, make_vehicle, optimizer
):
    d, v = _driver_and_vehicle(make_driver, make_vehicle, capacity=4)
    r1, r2 = _shared_pair(make_request)
    db.commit()
    batch = make_batch(requests=[r1, r2])
    db.commit()

    route = optimizer.optimize_batch(db, batch, vehicle_id=v.id, driver_id=d.id)

    assert set(route.request_ids) == {r1.id, r2.id}
    assert route.trip_key == batch.batch_code


def test_optimize_batch_missing_request_raises(db, make_batch, optimizer):
    batch = make_batch(requests=None, request_ids_json="[999999]")
    db.commit()

    with pytest.raises(ValueError, match="missing"):
        optimizer.optimize_batch(db, batch)


# ── Vehicle auto-selection ───────────────────────────────────────────────────

def test_select_vehicle_picks_nearest_available_with_capacity(
    db, make_request, make_vehicle, optimizer
):
    near = make_vehicle(name="Near", capacity=4, current_lat=ANCHOR_LAT, current_lng=ANCHOR_LNG)
    make_vehicle(name="Far", capacity=4, current_lat=ANCHOR_LAT + 1.0, current_lng=ANCHOR_LNG + 1.0)
    req = make_request(
        pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
        drop_lat=11.02, drop_lng=76.97,
        demand=1,
    )
    db.commit()

    chosen = optimizer._select_vehicle(db, [req], rules={})

    assert chosen.id == near.id


def test_select_vehicle_no_candidates_raises(db, make_request, make_vehicle, optimizer):
    make_vehicle(capacity=1, status="Busy")  # the only vehicle is unavailable
    req = make_request(
        pickup_lat=ANCHOR_LAT, pickup_lng=ANCHOR_LNG,
        drop_lat=11.02, drop_lng=76.97,
        demand=1,
    )
    db.commit()

    with pytest.raises(ValueError, match="No available vehicle"):
        optimizer._select_vehicle(db, [req], rules={})
