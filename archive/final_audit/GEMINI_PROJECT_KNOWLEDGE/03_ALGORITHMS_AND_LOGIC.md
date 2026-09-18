# Algorithms and Logic

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
