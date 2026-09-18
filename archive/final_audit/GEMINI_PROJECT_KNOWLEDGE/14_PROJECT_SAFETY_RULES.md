# Project Safety Rules

## DO NOT BREAK
1. **Evaluation Framework Determinism**: `evaluation/framework.py` relies on `random.seed()` and fixed config seeding. Do not introduce non-deterministic external API calls (e.g., unmocked Google Maps) into the evaluation pipeline.
2. **DMFE Phase 9 Gates**: The 5 sequential gates (A-E) in `decision_engine.py` are the core research claim. Do not alter their order or structural logic.
3. **Database Schema Migrations**: Do not rename columns in `SimulationRequest` or `Trip` that break the evaluation metrics.
4. **Learning Engine Loop**: The simulated execution model writes back to `complete_trip`. Do not bypass this hook.

## Regression Requirements
Any backend change must be followed by running `evaluation/verify_admfe.py` and ensuring no regressions in completion rate or batching correctness.
