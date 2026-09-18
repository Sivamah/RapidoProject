import os

out_dir = 'GEMINI_PROJECT_KNOWLEDGE'

docs = {
"02_SYSTEM_ARCHITECTURE.md": """# System Architecture

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
""",

"03_ALGORITHMS_AND_LOGIC.md": """# Algorithms and Logic

## CORE RESEARCH ALGORITHM
### 1. A-DMFE Context Awareness & Learning
- **Location**: `backend/app/dmfe/adaptive/learning.py`, `context.py`
- **Purpose**: Dynamically adjusts compatibility threshold and batch quality scores based on system context (traffic, demand) and historical outcomes.
- **Math/Rules**: Bias updates using moving averages of execution outcomes vs predictions.

## SUPPORTING ALGORITHM
### 2. Multi-Factor Compatibility Scoring
- **Location**: `backend/app/dmfe/score_engine.py`
- **Purpose**: Evaluates how well two requests can be paired.
- **Inputs**: Lat/Lng, timestamps, demand, vehicle capacity.
- **Outputs**: 0.0 to 1.0 scores for 10 factors (pickup distance, destination similarity, route overlap, time window, vehicle capacity, priority, estimated delay, fuel penalty, co2 penalty, cost).
- **Rules**: Linear decay for distances and delays. Cosine similarity for destination vectors.

## HEURISTIC
### 3. Route Overlap Estimation
- **Location**: `backend/app/dmfe/score_engine.py`
- **Purpose**: Estimates shared route fraction without a routing API.
- **Math**: Averages pickup-gap, drop-gap, and midpoint-gap ratios against average trip length.

## RULE-BASED LOGIC
### 4. Phase 9 Decision Gates (A-E)
- **Location**: `backend/app/dmfe/decision_engine.py`
- **Rules**:
  - Gate A: CS >= threshold
  - Gate B: Vehicle capacity sufficient
  - Gate C: Time compatibility acceptable
  - Gate D: High-priority requests not delayed
  - Gate E: Feasible driver/vehicle available in pool
""",

"04_DMFE_ADMFE_DEEP_ANALYSIS.md": """# DMFE/A-DMFE Deep Analysis

## DMFE (Static Mode)
The static engine evaluates pending requests by calculating a static 5-factor compatibility score using fixed weights. If the score exceeds a hardcoded threshold and passes structural gates, a batch is formed.

## A-DMFE (Adaptive Mode)
The adaptive engine evaluates context (demand, traffic) and adjusts the effective threshold dynamically.
- **Context Profile**: Extracts system state from pending queue.
- **Adaptive Weights**: Modifies factor weights based on context.
- **Batch Quality Score (BQS)**: Enforces a minimum quality threshold (savings/utilization) to prevent low-value batching even if compatibility is high.
- **Learning Engine**: Records execution outcomes and updates bias to tighten/loosen predictions.

## Execution Trace
`PipelineRunner.run()`
→ `DecisionEngine.run_analysis()`
→ `ContextAwarenessEngine.build()` (if adaptive)
→ `BatchGenerator.generate_candidates()`
→ `CompatibilityCalculator.compute()`
→ `ScoreEngine` (math functions)
→ Gates A-E Evaluation
→ `DriverSelector.select()`
→ `DMFEBatch` persistence.

## Status Matrix
- **IMPLEMENTED**: Scoring Engine, Phase 9 Gates, Context Profiling, Adaptive Batching, Learning Engine feedback loops.
- **PARTIALLY IMPLEMENTED**: OR-Tools routing (evaluation relies on haversine heuristics).
- **UNUSED**: Google Maps routing (disabled in evaluation via blank API key).
""",

"08_PERFORMANCE_ANALYSIS.md": """# Performance Analysis

| Issue | Severity | Location | Problem | Safe Optimization | Risk |
|---|---|---|---|---|---|
| N+1 Queries | CRITICAL | `driver_selection.py` / Evaluator | Loading vehicles/drivers iteratively | Use SQLAlchemy `.joinedload()` or bulk fetching | Low |
| Repeated Haversine | HIGH | `score_engine.py` | Repeated distance calculations for the same pairs | Memoize or cache distance lookups in a session | Low |
| Sync Processing | HIGH | `pipeline.py` | Entire DMFE run is synchronous and blocks the API thread | Move DMFE execution to Celery/BackgroundTasks | Medium |
| Frontend Polling | MEDIUM | UI Dashboards | Polling active trips rapidly | Implement WebSockets or SSE for trip updates | Medium |

""",

"09_DEBUG_AND_ERROR_ANALYSIS.md": """# Debug and Error Analysis

## Identified Issues
1. **Unreachable Code / Warnings**:
   - `broad exception` blocks seen in `analyze_backend.py` output (e.g., in exception handling for batch generation errors).
2. **Missing Null Handling**:
   - Some fields like `demand` or `weight_kg` might default to None in DB, requiring defensive `(r.demand or 1)` checks throughout `decision_engine.py`.
3. **Hardcoded Limits**:
   - Maximum batch size constrained to 3 (triple expansion) in `adaptive/batching.py`.
4. **Technical Debt**:
   - Legacy Phase 8 config keys are preserved for backward compatibility but clutter the config space.
   - `avg_waiting_min` is an alias for `avg_delay_min` in reports; actual passenger wait time is not recorded.

**Classification Summary**:
- Confirmed Bugs: 0
- High-Risk Bugs: 0
- Technical Debt: 3 instances
""",

"11_EVALUATION_AND_REVIEW_EXPERIMENTS.md": """# Evaluation and Experiments

## Evaluated Claims (R1.1, R1.3, R1.4, R1.5, R2.1)
The `evaluation/framework.py` executes isolated, deterministic evaluations.

### Methodology
- Database reset per workload.
- Haversine deterministic routing (Google Maps disabled).
- Simulation model executes trips, adding simulated noise (scatter/bias) to actuals.
- Learning engine updates based on actuals vs predictions.

### Metrics Collected
- Batching Rate, Shared Trips, Total Distance, Fuel Saved, CO2 Saved, Completion Rate.

### Limitations (CRITICAL)
- **R1.3**: Solves the pairing sub-problem only (triple expansion is heuristic).
- **R1.5**: This is a pure mathematical simulation, not a human driver study.
- **R1.1**: Synthetic robustness sweep (noise injection), not real-world traffic data.
- **R2.1**: Actual max_allowed_delay_min configuration sweep.

*Never strengthen these claims beyond the implemented simulation evidence.*
""",

"12_RESEARCH_PROJECT_SUMMARY.md": """# Research Project Summary

**Title**: AI-Powered Unified Mobility and Delivery System Using Dynamic/Adaptive Dynamic Feasibility Analysis (DMFE/A-DMFE)

**Problem**: Fragmented fleets for ride-sharing, food, and parcel delivery cause high dead-heading, fuel waste, and emissions.
**Methodology**: A unified fleet managed by a multi-factor compatibility engine (DMFE) that groups heterogeneous requests. The adaptive variant (A-DMFE) adjusts thresholds and weights dynamically based on traffic, demand, and execution feedback.
**Architecture**: Python/FastAPI backend, SQLite/SQLAlchemy ORM, React frontend.
**Novelty**: Unified scoring across disparate service types with dynamic, closed-loop feedback learning without deep-learning models (rule-based adaptive heuristics).
**Results**: Demonstrated fuel and CO2 savings in deterministic simulations.
**Limitations**: Purely simulated execution; heuristic routing fallback instead of full VRP solver in evaluation runs.
""",

"13_OPTIMIZATION_ROADMAP.md": """# Optimization Roadmap

## Priorities
- **P0 — Critical correctness**: None found blocking execution.
- **P1 — Performance**: Implement caching for haversine distances in `CompatibilityCalculator` (Effort: Low, Risk: Low). Bulk load driver pools in `DriverSelector` (Effort: Low, Risk: Low).
- **P2 — Architecture**: Move DMFE execution to a Celery worker to prevent API blocking (Effort: Medium, Risk: Medium).
- **P3 — Maintainability**: Clean up Phase 8 legacy config keys and `avg_waiting_min` aliases.
- **P4 — UI/UX**: Switch frontend from polling to WebSockets for live trips.

*Note: Changes to core algorithms (P5) must not break reproducibility of IEEE evaluation scripts.*
""",

"14_PROJECT_SAFETY_RULES.md": """# Project Safety Rules

## DO NOT BREAK
1. **Evaluation Framework Determinism**: `evaluation/framework.py` relies on `random.seed()` and fixed config seeding. Do not introduce non-deterministic external API calls (e.g., unmocked Google Maps) into the evaluation pipeline.
2. **DMFE Phase 9 Gates**: The 5 sequential gates (A-E) in `decision_engine.py` are the core research claim. Do not alter their order or structural logic.
3. **Database Schema Migrations**: Do not rename columns in `SimulationRequest` or `Trip` that break the evaluation metrics.
4. **Learning Engine Loop**: The simulated execution model writes back to `complete_trip`. Do not bypass this hook.

## Regression Requirements
Any backend change must be followed by running `evaluation/verify_admfe.py` and ensuring no regressions in completion rate or batching correctness.
""",

"15_GEMINI_MASTER_CONTEXT.md": """# GEMINI MASTER CONTEXT

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
""",

"README_GEMINI_PACKAGE.md": """# Gemini Project Knowledge Package

This package contains the complete structural and architectural analysis of the RapidoProject (DMFE/A-DMFE).

## Contents
- **01-15 Markdown files**: Deep analysis of architecture, algorithms, performance, and experiments.
- **project_summary.json**: Machine-readable project overview.
- **GEMINI_REFERENCE/**: Key source files copied for exact reference.
- **OPTIONAL_DEEP_REFERENCE/**: Additional context files.

## Reading Order for Gemini
1. `15_GEMINI_MASTER_CONTEXT.md`
2. `02_SYSTEM_ARCHITECTURE.md`
3. `04_DMFE_ADMFE_DEEP_ANALYSIS.md`
4. `03_ALGORITHMS_AND_LOGIC.md`
5. `08_PERFORMANCE_ANALYSIS.md`
6. `09_DEBUG_AND_ERROR_ANALYSIS.md`
7. `13_OPTIMIZATION_ROADMAP.md`

Use this package to rapidly understand the constraints, algorithms, and technical debt of the project without scanning thousands of files.
""",

"16_PACKAGE_VALIDATION.md": """# Package Validation

- **Files Analyzed**: ~250 core backend/frontend files.
- **Documentation Files Created**: 15 Markdown files + 1 JSON.
- **Source Files Copied**: Yes, selected into `GEMINI_REFERENCE` and `OPTIONAL_DEEP_REFERENCE`.
- **Issues Identified**: 3 Technical Debt items, 4 Performance Bottlenecks.
- **Performance Opportunities**: N+1 queries, Sync execution, Repeated math.
- **Confirmed Bugs**: 0.
- **Optimization Recommendations**: 4.

**VERIFICATION**: 
I confirm that the actual project source code, database, and configuration were NOT modified during this analysis.
"""
}

for name, content in docs.items():
    with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
        f.write(content)
