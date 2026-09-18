# Project File Inventory

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

