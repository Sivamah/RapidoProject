# Research Project Summary

**Title**: AI-Powered Unified Mobility and Delivery System Using Dynamic/Adaptive Dynamic Feasibility Analysis (DMFE/A-DMFE)

**Problem**: Fragmented fleets for ride-sharing, food, and parcel delivery cause high dead-heading, fuel waste, and emissions.
**Methodology**: A unified fleet managed by a multi-factor compatibility engine (DMFE) that groups heterogeneous requests. The adaptive variant (A-DMFE) adjusts thresholds and weights dynamically based on traffic, demand, and execution feedback.
**Architecture**: Python/FastAPI backend, SQLite/SQLAlchemy ORM, React frontend.
**Novelty**: Unified scoring across disparate service types with dynamic, closed-loop feedback learning without deep-learning models (rule-based adaptive heuristics).
**Results**: Demonstrated fuel and CO2 savings in deterministic simulations.
**Limitations**: Purely simulated execution; heuristic routing fallback instead of full VRP solver in evaluation runs.
