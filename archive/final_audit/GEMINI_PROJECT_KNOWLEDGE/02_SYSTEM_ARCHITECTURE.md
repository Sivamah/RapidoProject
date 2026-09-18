# System Architecture

## System Purpose
An AI-Powered Unified Mobility and Delivery System combining ride-sharing, food delivery, and parcel logistics into a single shared fleet using a Dynamic Multi-Service Feasibility Engine (DMFE) and its adaptive variant (A-DMFE).

## End-to-End Flow
Request
→ Request Collection (Mock Adapters)
→ Pending Queue (DB)
→ DMFE/A-DMFE (Batch Generator)
→ Compatibility Analysis (Score Engine, 10 factors)
→ Feasibility Decision (Decision Engine, Gates A-E)
→ Batch Formation (Adaptive Batching)
→ Driver Assignment (Driver Selector)
→ Trip Execution (Simulation via haversine)
→ Analytics (Learning Engine, Metrics)

*Note: OR-Tools integration appears documented conceptually but the core evaluation framework uses fallback heuristics and greedy assignment in the provided codebase snapshot.*

## Components
- **Frontend**: React-based dashboard for simulation control and metric viewing.
- **Backend**: FastAPI providing REST endpoints for DMFE engine triggering, config management, and dashboard data.
- **Engine**: The Python-based DMFE module containing rule-based logic, scoring algorithms, and a learning engine.
- **Database**: SQLite (SQLAlchemy) holding requests, trips, fleets, and configurations.
