# GEMINI MASTER CONTEXT

## PROJECT
**RapidoProject**: AI-Powered Unified Mobility and Delivery System Using DMFE/A-DMFE.

## ARCHITECTURE & CORE ALGORITHM
- **Backend**: FastAPI + SQLite (SQLAlchemy).
- **Engine**: A-DMFE evaluates pairs of requests across 10 mathematical factors (pickup distance, overlap, time, capacity, etc.).
- **Decision Engine**: 5 hard gates (CS > threshold, Capacity, Time gap, Priority, Driver availability).
- **A-DMFE**: Adjusts weights and thresholds dynamically using system context and a feedback learning engine.

## TESTS & EXPERIMENTS
- Fully simulated via `evaluation/framework.py`.
- Deterministic haversine routing.
- Validates R1.1, R1.3, R1.4, R1.5, R2.1.
- Limitation: Simulation only, no real-world drivers.

## TECHNICAL DEBT & SAFE OPTIMIZATIONS
- High DB polling, N+1 queries in driver assignment, repeated math calculations.
- Safe to optimize via caching and bulk fetching.

## HOW GEMINI SHOULD WORK ON THIS PROJECT
1. Inspect before modifying.
2. Preserve working behavior.
3. Never fabricate implementation.
4. Never claim unsupported AI/ML techniques (it uses rule-based adaptive heuristics, not neural networks).
5. Make minimal changes.
6. Run regression tests (`verify_admfe.py`) after changes.
7. Preserve reproducibility of evaluation scripts.
