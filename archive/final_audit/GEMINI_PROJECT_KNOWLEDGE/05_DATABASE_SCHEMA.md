# Database Schema

## Engine
- **Engine**: SQLite / PostgreSQL (SQLAlchemy)
- **Primary Configuration**: `dmfe_dev.db` for dev, `evaluation/experiments/eval.db` for eval.

## Core Tables

### SystemConfig
- **Purpose**: Dynamic settings and thresholds (weights, mode).
- **Columns**: id, category, key, value, data_type, updated_at.

### SimulationRequest
- **Purpose**: Represents a ride, parcel, or food delivery request.
- **Columns**: id, request_type, pickup_lat, pickup_lng, drop_lat, drop_lng, demand, weight_kg, status, priority.

### Vehicle & Driver
- **Purpose**: Represents fleet entities.
- **Columns (Vehicle)**: id, provider_id, vehicle_type, capacity, mileage_kmpl, status.
- **Columns (Driver)**: id, assigned_vehicle_id, status, current_lat, current_lng.

### DMFEBatch
- **Purpose**: Logs decision engine batches.
- **Columns**: id, batch_code, request_ids_json, compatibility_score, decision, reason_json, factor_scores_json, status, estimated_delay_min.

### DMFEAnalysisRun
- **Purpose**: Aggregates a single run's decisions.
- **Columns**: id, total_pending, batches_created, rejected_count, avg_compatibility_score, threshold_used.

### Trip
- **Purpose**: Actual execution record for assigned drivers.
- **Columns**: id, driver_id, vehicle_id, status, max_delay_min, utilization_pct, fuel_l.
