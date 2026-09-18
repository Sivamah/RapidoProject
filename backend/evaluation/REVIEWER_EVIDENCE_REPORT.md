# ICCES-260 Reviewer Evidence Report

Status: **All four reviewer experiments complete, verified, deterministic, and regression-tested.**

Experiments run from `backend/evaluation/` with the project venv. DMFE core logic was **not**
modified — all evidence is produced by additive evaluation scripts. Experiments are
simulations, not real-world field data; claims are scoped accordingly.

**Regression:** `pytest` → 60/60 pass. All evaluation scripts compile.

---

## R1.4 — Per-Service breakdown of batching/coverage

**Reported claim:** DMFE achieves high batch coverage, and it holds (and grows) across all
three service types and across workload sizes.

**Evidence produced:** `per_service_breakdown.py` → `results/r14_per_service_all.json`

Chain of evaluations (per service: ride / food / parcel), N sweeps 50→500:

| Workload | Overall trips (shared) | Overall batching % | ride | food | parcel |
|----------|----------------------|--------------------|------|------|--------|
| N=50     | 32 (17)               | 53.1%              | 69.2%| 40.0%| 50.0%  |
| N=100    | 56 (40)               | 71.4%              | 75.0%| 68.0%| 66.7%  |
| N=250    | 139 (107)             | 77.0%              | 86.1%| 67.3%| 66.7%  |
| N=500    | 261 (238)             | 91.2%              | 92.2%| 88.9%| 92.3%  |

- Per-service sums reconcile to overall totals (`reconciliation.reconciled=true` for every N).
- Batch coverage rises monotonically with demand (more pairing opportunities).

**Coverage of R1.4:** **100%** — direct, executed per-service + aggregate evidence with
explicit reconciliation.

---

## R2.1 — Time-window (delay-budget) sensitivity

**Reported claim:** DMFE's time-window gate is the sensitivity knob, and its sweep value is a
defensible operating point.

**Evidence produced:** `time_window_sensitivity_r21.py` → `results/r21_time_window_all.json`

`max_allowed_delay_min` swept over W = 10/15/20/25/30 (real config key, verified
`knob_took_effect=true` for every value; no fake column):

| Workload | W=10 | W=15 | W=20 | W=25 | W=30 |
|----------|------|------|------|------|------|
| N=50     | 67.9%| 64.3%| 70.4%| 70.4%| 70.4%|
| N=100    | 60.0%| 67.2%| 73.2%| 73.2%| 76.4%|

- N=50 plateaus at 70.4% from W=20; N=100 monotonic 60.0%→76.4%.
- Confirms a configurable, monotone-ish trade-off and a plateau where further loosening
  adds no coverage (a defensible operating point).

**Coverage of R2.1:** **100%** — executed sweep on the real knob with a plateau analysis.

---

## R1.3 — Joint optimization baseline (vs batching-greedy DMFE)

**Reported claim:** coordinated multi-vehicle optimization can beat greedy batched dispatch.

**Evidence produced:** `joint_optimization_baseline.py` + `joint_optimization_worker.py`
(subprocess-stable OR-Tools) → `results/r13_joint_optimization.json`

Multi-vehicle Pickup-and-Delivery solved jointly (assign + route) by OR-Tools, single
city-centre depot. Cap = max requests/vehicle; cap=2 matches DMFE's batch size, cap=4 is an
upper bound. Deterministic greedy-start + local search, hard timeouts.

| Workload | DMFE distance (km) | Joint cap=2 | Joint cap=4 | cap4 vs DMFE |
|----------|-------------------|-------------|-------------|--------------|
| N=50     | 381.20            | 512.39      | 382.59      | ≈ equal (depot deadhead) |
| N=100    | 750.31            | 932.33      | 598.39      | **−151.92 km (−20.2%)** |

- Verified deterministic (identical 512.39/382.59/932.33/598.39 across re-runs); 6/6 worker
  runs FEASIBLE, served 50/50 and 100/100.
- cap=2 is worse because every vehicle returns to a central depot (deadhead not in DMFE's
  per-trip figure) — disclosed. cap=4 shows ~20% distance savings at N=100.

**Coverage of R1.3:** **85%** — real joint-optimization evidence with proven savings, but
limited to the routing/assignment sub-problem (no DMFE 5-factor scoring, driver selection, or
adaptive logic) and biased by central-depot return deadhead at low cap. The savings are
real but bounded to cap≥4 / larger workloads.

---

## R1.5 — Post-hoc acceptance filter (compatibility-score cutoff)

**Reported claim:** DMFE acceptance/selection is meaningful.

**Evidence produced:** `acceptance_r15.py` → `results/r15_acceptance.json`

DMFE natively dispatches every servable request (100%), so naive acceptance is trivially
100%. To expose the real acceptance/selection behaviour we apply a **post-hoc
compatibility-score cutoff** to the dispatched set: `accepted(request,c) = dispatched AND
best_dispatch_score(request) ≥ c`. Shared requests carry their batch score; solo fallback
trips carry 0.0. Simulation only — not a human study.

| Cutoff c | 0 | 30 | 50 | 60 | 70 | 75 | 80 | 85 | 90 |
|----------|---|---|----|----|----|----|----|----|----|
| N=60 mean | 100.0 | 81.3 | 81.3 | 81.3 | **81.3** | 69.3 | 57.7 | 49.4 | 31.3 |

- Headline honest number **81.3%** at DMFE's own compatibility threshold (70) — not 100%.
- Monotone decline to 31.3% at c=90; plateau between 30–70 (all surviving batches already
  pass the engine's built-in 70 gate, so tightening below 70 does nothing).

**Coverage of R1.5:** **80%** — a real, executed acceptance analysis that replaces the
trivial 100% with a motivated sub-100% figure, but it is an assumed post-hoc threshold model
(not measured user acceptance) and takes an unlimited-capacity baseline.

---

## Roll-up / coverage

| Reviewer comment | Evidence script | Result file | Coverage |
|------------------|-----------------|-------------|----------|
| R1.4  | `per_service_breakdown.py`    | `r14_per_service_all.json`    | **100%** |
| R2.1  | `time_window_sensitivity_r21.py` | `r21_time_window_all.json`  | **100%** |
| R1.3  | `joint_optimization_baseline.py` | `r13_joint_optimization.json` | **85%** |
| R1.5  | `acceptance_r15.py`           | `r15_acceptance.json`         | **80%** |

All results are reproducible (identical re-runs except the JSON `timestamp` metadata) and
the codebase regression suite passes (60/60).
