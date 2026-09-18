# DEBUG_REPORT — ICCES-260 Reviewer-Experiment Package (DMFE / A-DMFE)

**Status:** COMPLETE — all five reviewer-experiment scripts created from
scratch, executed against the current DMFE / A-DMFE pipeline, validated,
made reproducible, and regressed.

## 1. Task outcome

The five reviewer experiments were never present anywhere in the repository
(working tree, git history, or results).  Per the approved decision they were
**created from scratch** inside `backend/evaluation/`, executed, and validated.
Nothing outside `backend/evaluation/` was modified, and the production/dev
database `dmfe_dev.db` was never touched.

## 2. Files delivered

| File | Reviewer mapping | Status |
|------|------------------|--------|
| `evaluation/per_service_breakdown.py` | R1.4 | ✅ compiled + ran, reconciled |
| `evaluation/exact_matching_baseline.py` | R1.3 | ✅ compiled + ran, stdlib-only |
| `evaluation/robustness_r11.py` | R1.1 | ✅ compiled + ran, 8/8 profiles |
| `evaluation/time_window_sensitivity_r21.py` | R2.1 | ✅ compiled + ran, knob verified |
| `evaluation/acceptance_r15.py` | R1.5 | ✅ compiled + ran, simulation |
| `evaluation/README.md` | — | ✅ delivered |
| `evaluation/DEBUG_REPORT.md` | — | ✅ this file |
| `evaluation/results/r1*.json`, `results/r21_time_window.json` | — | ✅ 5 result reports |

## 3. Verification performed

1. **Compile:** all five scripts pass `py_compile`.
2. **Execution:** all five run to completion against the isolated
   `experiments/eval.db`; none fabricate rows (each aborts if it cannot
   reproduce its required workload).
3. **Aggregate validation:** every result JSON was reloaded and its internal
   totals / percentages recomputed — 56 checks, 0 failures (per-service
   reconciliation, per-priority rates, completion rates, batching rates).
4. **Reproducibility:** each script is seeded deterministically.  Initial
   testing found run-to-run drift in the *wave* phase of the scripts that
   drive the real pipeline over multiple waves (`robustness_r11.py`,
   `time_window_sensitivity_r21.py`, `acceptance_r15.py`).  Root cause and fix
   in §5.  After the fix, **all five scripts are bit-for-bit reproducible
   across 3 consecutive independent runs** (15 script executions; only the
   `timestamp` field differs).
5. **Regression:** see §6.

## 4. Result highlights

- **R1.1 (robustness):** 8 profiles ran (LOW/HIGH × 4 temporal shapes).
  Single-pass **batching rate responds to temporal shape** — e.g. HIGH
  morning/evening peak ≈ 83% vs midday flat 43% / night sparse 57%; LOW peak
  ≈ 47–50% vs flat 7% / sparse 11%.  All profiles dispatch 100% of requests.
- **R1.3 (exact vs greedy pairing, sub-problem):** on a 14-request pool with
  the real compatibility scores, greedy total 611.7 vs exact optimum 613.1
  → the current greedy pairing is within **+0.23%** of the optimum on this
  sub-problem (7 pairs matched by both; exact trades pair choices slightly).
- **R1.4 (per-service):** ride 24 / food 24 / parcel 12 requests; batching
  ride 68.4% / food 53.8% / parcel 25.0%; overall batching 62.9%;
  reconciliation OK (trips, shared, dispatched all tally).
- **R1.5 (acceptance simulation):** under the **assumed model**
  (priority-weighted dispatch + completion through the trip lifecycle),
  simulated acceptance and fulfillment = 100% mean over 5 repeats.  Explicitly
  a simulation, not a human study.
- **R2.1 (time-window/max-delay sweep):** `SystemConfig.max_allowed_delay_min`
  swept 10→30 min; the engine's read-back equals the value at every point
  (knob genuinely takes effect).  Batching rises as the window widens:
  ~56% @10 min → ~65% @15 min → ~70% @20–30 min (saturated).

## 5. Key debug finding — wave-phase reproducibility

The experiments that run the real DMFE pipeline over **multiple waves**
(`r11`, `r21`, `r15`) initially were not bit-for-bit reproducible across
separate process runs.  Debugging showed:

- The single-pass dispatch **is** deterministic given a fixed seed.
- The **wave phase** was not: each later wave's dispatch uses the module-global
  Python `random`, which has advanced through prior waves and trip completion,
  and the harness's independent execution RNG (`_exec_rng`) likewise advances
  across every simulated trip in iteration order.  With large far-future
  timestamp profiles and driver-availability racing in later waves, this leaked
  non-determinism into wave totals (and, transiently, into recorded metrics).

**Fix (contained to the experiment scripts, no core changes):** the wave loop
in each affected script now reseeds both the dispatch RNG and the execution RNG
deterministically from `seed + wave_index` before each wave:

```python
random.seed(seed + 1000 + waves)
runner._exec_rng = random.Random(seed + 9000 + waves)
```

This makes the wave phase fully deterministic without altering the real
pipeline.  Verified by 3 consecutive full runs (see §3).

## 6. Regression status

- `pytest -q` — pass (68 tests).
- `verify_all.py` / `verify_demo.py` / `verify_admfe.py` /
  `verify_unified_scoring.py` — pass.
- `import app.main` — loads.
- No files changed outside `backend/evaluation/`; `dmfe_dev.db` mtime/hash
  unchanged (all session writes confined to the isolated `eval.db`).

## 7. Honesty / scope notes

- R1.5 is a **simulation** under an explicitly stated assumed model; it makes
  no human-study or user-preference claims.
- R1.1 varies the `request_timestamp` field the engine actually reads; it does
  **not** inject a fake per-request time-window column the engine does not
  support.
- All metrics are over synthetic requests from the existing
  `generate_simulation_requests` harness.
- `exact_matching_baseline.py` implements the exact max-weight matching with the
  Python standard library (subset DP) — networkx is intentionally not used
  (not installed, not in `requirements.txt`).
