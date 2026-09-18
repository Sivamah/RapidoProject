import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import func, String
from sqlalchemy.orm import Session

from app.db.models import Driver, Vehicle, Provider, DriverAssignmentHistory

logger = logging.getLogger(__name__)

SAMPLE_COORDINATES = [
    (11.0168, 76.9558), # Gandhipuram
    (10.9980, 76.9660), # Ukkadam
    (11.0280, 76.9400), # R.S. Puram
    (11.0400, 76.9900), # Peelamedu
    (11.0800, 76.9950), # Saravanampatti
    (11.0000, 77.0300), # Singanallur
]

SEED_DRIVERS_DATA = [
    {"name": f"Driver {i}", "phone": f"+91 9{i%10}8421{i:04d}", "email": f"driver{i}@example.com", "status": "Available", "license": f"TN37 2021{i:06d}"}
    for i in range(1, 21)
]

class DriverService:
    """Service layer managing Drivers, Vehicles, Location tracking, and Assignment logs."""

    SEED_FLAG_KEY = "driver.seeded"

    def _is_seeded(self, db: Session) -> bool:
        from app.db.models import SystemConfig
        row = (
            db.query(SystemConfig)
            .filter(SystemConfig.key == self.SEED_FLAG_KEY)
            .first()
        )
        return row is not None and str(row.value).lower() == "true"

    def seed_initial_data_if_needed(self, db: Session):
        """Ensure initial realistic drivers and vehicles exist for demo providers.

        Runs only once (guarded by the SystemConfig 'driver.seeded' flag) and is
        invoked from the app lifespan, never from read endpoints.  It no longer
        mutates existing vehicles/drivers, so a GET /drivers cannot fight the
        DMFE availability gate or cause SQLite write-lock contention.
        """
        try:
            from app.db.models import SystemConfig
            driver_count = db.query(Driver).count()
            if self._is_seeded(db) and driver_count > 0:
                return

            providers = db.query(Provider).all()
            if not providers:
                p = Provider(name="Default Provider", provider_type="3PL", category="Logistics")
                db.add(p)
                db.commit()
                db.refresh(p)
                providers = [p]

            driver_count = db.query(Driver).count()
            if driver_count < 20:
                coords = SAMPLE_COORDINATES
                existing_driver_phones = {d.phone for d in db.query(Driver).all()}
                for i, d in enumerate(SEED_DRIVERS_DATA):
                    if d["phone"] in existing_driver_phones:
                        continue
                    p = providers[i % len(providers)]
                    lat, lng = coords[i % len(coords)]
                    driver = Driver(
                        provider_id=p.id,
                        name=d["name"],
                        phone=d["phone"],
                        email=d["email"],
                        status=d["status"],
                        license_number=d["license"],
                        current_lat=lat,
                        current_lng=lng,
                    )
                    db.add(driver)
                db.commit()

            vehicle_count = db.query(Vehicle).count()
            if vehicle_count < 15:
                coords = SAMPLE_COORDINATES
                vehicle_types = ["Bike", "EV Bike", "Auto", "Mini Truck"]
                for i in range(vehicle_count + 1, 16):
                    p = providers[i % len(providers)]
                    lat, lng = coords[i % len(coords)]
                    v_type = vehicle_types[i % len(vehicle_types)]
                    capacity = 1 if "Bike" in v_type else 2
                    if v_type == "Mini Truck":
                        capacity = 4

                    vehicle = Vehicle(
                        provider_id=p.id,
                        name=f"Vehicle {i}",
                        vehicle_type=v_type,
                        registration_number=f"TN-37-X-{1000 + i}",
                        capacity=capacity,
                        status="Available",
                        current_lat=lat,
                        current_lng=lng,
                    )
                    db.add(vehicle)
                db.commit()

            # Persist the seed guard so subsequent requests never write again.
            flag = (
                db.query(SystemConfig)
                .filter(SystemConfig.key == self.SEED_FLAG_KEY)
                .first()
            )
            if flag is None:
                db.add(SystemConfig(
                    category="system",
                    key=self.SEED_FLAG_KEY,
                    value="true",
                    data_type="bool",
                ))
                db.commit()
        except Exception as exc:
            logger.warning("seed_initial_data_if_needed error: %s", exc)

    def get_drivers(
        self,
        db: Session,
        search: Optional[str] = None,
        provider_id: Optional[int] = None,
        status: Optional[str] = None,
        availability: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = db.query(Driver)

        if provider_id and provider_id != 0:
            query = query.filter(Driver.provider_id == provider_id)
        if status and status.lower() != "all":
            query = query.filter(func.lower(Driver.status) == status.lower())
        if availability and availability.lower() != "all":
            query = query.filter(func.lower(Driver.status) == availability.lower())

        if search:
            s_lower = search.lower()
            query = query.filter(
                (func.lower(Driver.name).contains(s_lower)) |
                (func.lower(Driver.phone).contains(s_lower)) |
                (func.lower(Driver.email).contains(s_lower)) |
                (func.lower(Driver.license_number).contains(s_lower)) |
                (func.cast(Driver.id, String).contains(s_lower))
            )

        drivers = query.order_by(Driver.created_at.desc()).limit(limit).all()

        # Targeted lookups — only fetch providers/vehicles referenced by the
        # returned driver rows, not the entire table (previously O(all rows)).
        provider_ids = {d.provider_id for d in drivers if d.provider_id}
        vehicle_ids  = {d.assigned_vehicle_id for d in drivers if d.assigned_vehicle_id}

        providers = (
            {p.id: p.name for p in db.query(Provider.id, Provider.name)
             .filter(Provider.id.in_(provider_ids)).all()}
            if provider_ids else {}
        )
        vehicles = (
            {v.id: v.name for v in db.query(Vehicle.id, Vehicle.name)
             .filter(Vehicle.id.in_(vehicle_ids)).all()}
            if vehicle_ids else {}
        )

        return [
            self._driver_dict(d, providers.get(d.provider_id, "Unassigned"), vehicles.get(d.assigned_vehicle_id, "None"))
            for d in drivers
        ]

    @staticmethod
    def _driver_dict(d: Driver, provider_name: str, vehicle_name: str) -> Dict[str, Any]:
        """Single source of truth for the Driver response shape — shared by
        `get_drivers` (bulk, pre-fetched name maps) and `serialize_driver`
        (single already-loaded row, e.g. right after a create/update)."""
        return {
            "id": d.id,
            "name": d.name,
            "phone": d.phone or "",
            "email": d.email or "",
            "provider_id": d.provider_id,
            "provider_name": provider_name,
            "status": d.status or "Available",
            "license_number": d.license_number or "",
            "current_lat": d.current_lat or 11.0168,
            "current_lng": d.current_lng or 76.9558,
            "assigned_vehicle_id": d.assigned_vehicle_id,
            "assigned_vehicle_name": vehicle_name,
            "created_at": d.created_at,
        }

    def serialize_driver(self, db: Session, driver: Driver) -> Dict[str, Any]:
        """Serialize ONE already-loaded Driver row (e.g. just created/updated
        and `db.refresh()`-ed) without re-running the filtered, ordered,
        limited `get_drivers` list query — and without that method's own
        full Provider/Vehicle IN-lookup, which is unnecessary here since at
        most one provider name and one vehicle name are ever needed.
        """
        provider_name = "Unassigned"
        if driver.provider_id:
            row = db.query(Provider.name).filter(Provider.id == driver.provider_id).first()
            if row:
                provider_name = row[0]
        vehicle_name = "None"
        if driver.assigned_vehicle_id:
            row = db.query(Vehicle.name).filter(Vehicle.id == driver.assigned_vehicle_id).first()
            if row:
                vehicle_name = row[0]
        return self._driver_dict(driver, provider_name, vehicle_name)

    def get_driver_stats(self, db: Session) -> Dict[str, int]:
        # Single GROUP BY query instead of 4 separate COUNT round-trips.
        rows = (
            db.query(func.lower(Driver.status), func.count(Driver.id))
            .group_by(func.lower(Driver.status))
            .all()
        )
        counts = {status: cnt for status, cnt in rows}
        total = sum(counts.values())
        return {
            "total_drivers": total,
            "available_drivers": counts.get("available", 0),
            "busy_drivers": counts.get("busy", 0),
            "offline_drivers": counts.get("offline", 0),
        }

    def get_vehicles(
        self,
        db: Session,
        search: Optional[str] = None,
        provider_id: Optional[int] = None,
        vehicle_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = db.query(Vehicle)

        if provider_id and provider_id != 0:
            query = query.filter(Vehicle.provider_id == provider_id)
        if vehicle_type and vehicle_type.lower() != "all":
            query = query.filter(func.lower(Vehicle.vehicle_type) == vehicle_type.lower())
        if status and status.lower() != "all":
            query = query.filter(func.lower(Vehicle.status) == status.lower())

        if search:
            s_lower = search.lower()
            query = query.filter(
                (func.lower(Vehicle.name).contains(s_lower)) |
                (func.lower(Vehicle.registration_number).contains(s_lower)) |
                (func.lower(Vehicle.vehicle_type).contains(s_lower)) |
                (func.lower(Vehicle.fuel_type).contains(s_lower))
            )

        vehicles = query.order_by(Vehicle.created_at.desc()).limit(limit).all()

        # Targeted lookups — only fetch providers/drivers referenced by the
        # returned vehicle rows, not the full tables.
        provider_ids = {v.provider_id for v in vehicles if v.provider_id}
        driver_ids   = {v.current_driver_id for v in vehicles if v.current_driver_id}

        providers = (
            {p.id: p.name for p in db.query(Provider.id, Provider.name)
             .filter(Provider.id.in_(provider_ids)).all()}
            if provider_ids else {}
        )
        drivers = (
            {d.id: d.name for d in db.query(Driver.id, Driver.name)
             .filter(Driver.id.in_(driver_ids)).all()}
            if driver_ids else {}
        )

        return [
            self._vehicle_dict(v, providers.get(v.provider_id, "Unassigned"), drivers.get(v.current_driver_id, "Unassigned"))
            for v in vehicles
        ]

    @staticmethod
    def _vehicle_dict(v: Vehicle, provider_name: str, driver_name: str) -> Dict[str, Any]:
        """Single source of truth for the Vehicle response shape — shared by
        `get_vehicles` (bulk, pre-fetched name maps) and `serialize_vehicle`
        (single already-loaded row, e.g. right after a create/update)."""
        return {
            "id": v.id,
            "name": v.name,
            "vehicle_type": v.vehicle_type,
            "registration_number": v.registration_number or f"TN-37-AB-{v.id + 1000}",
            "capacity": v.capacity or 1,
            "fuel_type": v.fuel_type or "Petrol",
            "provider_id": v.provider_id,
            "provider_name": provider_name,
            "status": v.status or "Available",
            "cost_per_km": v.cost_per_km or 10.0,
            "mileage_kmpl": v.mileage_kmpl or 15.0,
            "current_lat": v.current_lat or 11.0168,
            "current_lng": v.current_lng or 76.9558,
            "current_driver_id": v.current_driver_id,
            "current_driver_name": driver_name,
            "is_active": bool(v.is_active),
        }

    def serialize_vehicle(self, db: Session, vehicle: Vehicle) -> Dict[str, Any]:
        """Serialize ONE already-loaded Vehicle row without re-running the
        filtered `get_vehicles` list query (and its own Provider/Driver
        IN-lookup) just to re-fetch the row the caller already has."""
        provider_name = "Unassigned"
        if vehicle.provider_id:
            row = db.query(Provider.name).filter(Provider.id == vehicle.provider_id).first()
            if row:
                provider_name = row[0]
        driver_name = "Unassigned"
        if vehicle.current_driver_id:
            row = db.query(Driver.name).filter(Driver.id == vehicle.current_driver_id).first()
            if row:
                driver_name = row[0]
        return self._vehicle_dict(vehicle, provider_name, driver_name)

    def get_vehicle_stats(self, db: Session) -> Dict[str, int]:
        # Single GROUP BY query instead of 4 separate COUNT round-trips.
        rows = (
            db.query(func.lower(Vehicle.status), func.count(Vehicle.id))
            .group_by(func.lower(Vehicle.status))
            .all()
        )
        counts = {status: cnt for status, cnt in rows}
        total = sum(counts.values())
        return {
            "total_vehicles": total,
            "available_vehicles": counts.get("available", 0),
            "vehicles_in_service": counts.get("busy", 0),
            "maintenance_vehicles": counts.get("maintenance", 0),
        }

    def get_vehicle_locations(self, db: Session) -> List[Dict[str, Any]]:
        vehicles = db.query(Vehicle).all()

        # Targeted lookups for the referenced IDs only.
        provider_ids = {v.provider_id for v in vehicles if v.provider_id}
        driver_ids   = {v.current_driver_id for v in vehicles if v.current_driver_id}
        providers = (
            {p.id: p.name for p in db.query(Provider.id, Provider.name)
             .filter(Provider.id.in_(provider_ids)).all()}
            if provider_ids else {}
        )
        drivers = (
            {d.id: d.name for d in db.query(Driver.id, Driver.name)
             .filter(Driver.id.in_(driver_ids)).all()}
            if driver_ids else {}
        )

        # Positions are reported, never invented.  This used to fall back to
        # `SAMPLE_COORDINATES[i % 6]`, which placed any vehicle with no recorded
        # position on a canned Coimbatore landmark — a fabricated vehicle on the
        # live operations map, indistinguishable from a real one.  A vehicle
        # without a usable coordinate is now omitted from the location feed;
        # fleet composition still comes from /api/vehicles.  The registration
        # number is likewise reported as-is (empty when unknown) rather than
        # synthesised into a plausible-looking plate.
        result = []
        skipped = 0
        for v in vehicles:
            lat, lng = v.current_lat, v.current_lng
            if lat is None or lng is None or (lat == 0 and lng == 0):
                skipped += 1
                continue
            result.append({
                "vehicle_id": v.id,
                "vehicle_name": v.name,
                "vehicle_type": v.vehicle_type,
                "registration_number": v.registration_number or "",
                "provider_name": providers.get(v.provider_id, "Unassigned"),
                "driver_name": drivers.get(v.current_driver_id, "Unassigned"),
                "status": v.status or "Available",
                "lat": float(lat),
                "lng": float(lng),
            })
        if skipped:
            logger.info(
                "vehicle locations: omitted %d vehicle(s) without a recorded position",
                skipped,
            )
        return result

    def get_assignment_history(self, db: Session, limit: int = 100) -> List[Dict[str, Any]]:
        items = db.query(DriverAssignmentHistory).order_by(DriverAssignmentHistory.assignment_time.desc()).limit(limit).all()

        if not items:
            # Seed synthetic history logs if empty
            drivers = db.query(Driver).limit(5).all()
            vehicles = db.query(Vehicle).limit(5).all()
            if drivers and vehicles:
                for i in range(min(len(drivers), len(vehicles))):
                    hist = DriverAssignmentHistory(
                        driver_id=drivers[i].id,
                        vehicle_id=vehicles[i].id,
                        driver_name=drivers[i].name,
                        vehicle_name=vehicles[i].name,
                        status="Active" if i == 0 else "Completed",
                    )
                    db.add(hist)
                db.commit()
                items = db.query(DriverAssignmentHistory).order_by(DriverAssignmentHistory.assignment_time.desc()).limit(limit).all()

        result = []
        for h in items:
            a_time = h.assignment_time or datetime.now(timezone.utc)
            if a_time.tzinfo is None:
                a_time = a_time.replace(tzinfo=timezone.utc)

            c_time_str = None
            if h.completion_time:
                c_t = h.completion_time
                if c_t.tzinfo is None:
                    c_t = c_t.replace(tzinfo=timezone.utc)
                c_time_str = c_t.strftime("%Y-%m-%d %I:%M %p")

            result.append({
                "id": h.id,
                "driver_id": h.driver_id,
                "driver_name": h.driver_name or f"Driver #{h.driver_id}",
                "vehicle_id": h.vehicle_id,
                "vehicle_name": h.vehicle_name or f"Vehicle #{h.vehicle_id}",
                "assignment_time": a_time.strftime("%Y-%m-%d %I:%M %p"),
                "completion_time": c_time_str,
                "status": h.status or "Active",
            })
        return result


driver_service = DriverService()
