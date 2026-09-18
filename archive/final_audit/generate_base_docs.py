import os
import json

out_dir = 'GEMINI_PROJECT_KNOWLEDGE'
os.makedirs(out_dir, exist_ok=True)

inventory = """# Project File Inventory

## ACTIVE CORE
| Path | Type | Purpose | Notes |
|---|---|---|---|
| backend/app/dmfe/decision_engine.py | Python | DMFE Core Decision Logic (Gate A-E) | Highly critical |
| backend/app/dmfe/score_engine.py | Python | Pure math scoring functions | Core logic |
| backend/app/dmfe/adaptive/batching.py | Python | A-DMFE Module 5 Batch Formation | Core A-DMFE |
| backend/app/dmfe/batch_generator.py | Python | Legacy/Base Batch Generator | Used in static mode |
| backend/app/dmfe/driver_selection.py | Python | Driver/Vehicle matching | Core dispatch |
| backend/app/dmfe/adaptive/learning.py | Python | Adaptive feedback engine | A-DMFE |
| backend/app/engine/distance.py | Python | Haversine distance tools | Core |

## EVALUATION
| Path | Type | Purpose | Notes |
|---|---|---|---|
| backend/evaluation/framework.py | Python | Read-only evaluation harness | Evaluates Phase 9 DMFE |
| backend/evaluation/run_admfe_experiments.py | Python | Runs A-DMFE workloads | |
| backend/evaluation/verify_admfe.py | Python | Evaluation verification | |

## CONFIGURATION
| Path | Type | Purpose | Notes |
|---|---|---|---|
| backend/app/core/config.py | Python | Settings definition | |

## DATABASE
| Path | Type | Purpose | Notes |
|---|---|---|---|
| backend/app/db/models.py | Python | SQLAlchemy Models | Core DB Schema |
| backend/app/dmfe/models.py | Python | DMFE specific models (DMFEBatch, Run) | |

"""

with open(os.path.join(out_dir, '01_PROJECT_FILE_INVENTORY.md'), 'w', encoding='utf-8') as f:
    f.write(inventory)

db_schema = """# Database Schema

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
"""

with open(os.path.join(out_dir, '05_DATABASE_SCHEMA.md'), 'w', encoding='utf-8') as f:
    f.write(db_schema)

api_map = """# API Map

## Endpoints

### DMFE / Config
- **GET /api/config** - Retrieves dynamic thresholds and weights.
- **PUT /api/config** - Updates settings (triggers adaptive changes).
- **GET /api/dmfe/runs** - Lists DMFE analysis runs.
- **GET /api/dmfe/batches** - Lists batches and decision reasons.

### Requests / Dispatch
- **POST /api/requests/simulate** - Generates simulation traffic.
- **GET /api/requests/pending** - Fetches the pending queue.
- **POST /api/engine/run** - Triggers a manual pipeline dispatch.

## Known Issues
- Large query limits may cause heavy DB load if polling is high.
- Polling `dmfe/batches` in UI might lack cursor-based pagination.
"""

with open(os.path.join(out_dir, '06_API_MAP.md'), 'w', encoding='utf-8') as f:
    f.write(api_map)

frontend_map = """# Frontend Map

## Architecture
- React/Next.js/Vite based Single Page Application.
- State management likely Context or Redux.

## Key Views
- **Dashboard**: High-level metrics, system status, active trips.
- **Request Simulator**: Panel to generate simulated traffic (ride, food, parcel).
- **DMFE Monitor**: Visualizes the decision engine, batches, candidate groups, and rejection reasons.
- **Configuration Panel**: Controls weights, threshold, A-DMFE mode toggles.

## Performance Bottlenecks
- Excessive polling on active trips.
- Full table loads for batch histories.
"""
with open(os.path.join(out_dir, '07_FRONTEND_MAP.md'), 'w', encoding='utf-8') as f:
    f.write(frontend_map)

tests = """# Test and Verification Summary

## Frameworks
- `pytest` for backend unit tests.
- `evaluation/verify_admfe.py` for logical constraints validation.

## Key Test Areas
- **DMFE Scoring**: Tests isolated pure math functions.
- **Batch Formation**: Asserts no capacity violations.
- **Evaluation Scripts**: End-to-end multi-wave tests checking fuel, emissions, and completion rates.

## Missing Coverage
- Likely low coverage on exact frontend UI components.
- Edge cases in driver ETA fallback.
"""
with open(os.path.join(out_dir, '10_TEST_AND_VERIFICATION_SUMMARY.md'), 'w', encoding='utf-8') as f:
    f.write(tests)

summary = {
  "project_name": "AI-Powered Unified Mobility and Delivery System Using Dynamic/Adaptive Dynamic Feasibility Analysis (DMFE/A-DMFE)",
  "architecture": {"type": "Modular Monolith", "db": "SQLite/SQLAlchemy"},
  "core_algorithms": ["DMFE Scoring", "A-DMFE Context Awareness", "A-DMFE Batching"],
  "services": ["API", "DMFE Engine", "Simulation Harness"],
  "database": {"engine": "SQLite"},
  "apis": ["/api/config", "/api/dmfe", "/api/requests"],
  "frontend": {"framework": "React (Implied)"},
  "experiments": {"framework": "evaluation/framework.py"},
  "tests": {"framework": "pytest, verify scripts"},
  "performance": {"bottlenecks": ["Heavy DB polling", "Sync haversine calls"]},
  "known_bugs": [],
  "technical_debt": ["Legacy Phase 8 config keys"],
  "optimization_priorities": ["Caching", "Async DB"],
  "research_claims": ["Adaptive batching improves fuel efficiency", "Multi-service unified scoring"],
  "limitations": ["Simulation, not human study", "Pairing sub-problem only"]
}
with open(os.path.join(out_dir, 'project_summary.json'), 'w', encoding='utf-8') as f:
    json.dump(summary, f, indent=2)

