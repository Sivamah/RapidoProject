# DMFE/A-DMFE Deep Analysis

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
