# Reviewer / IEEE Claim Audit

Scope: this audit covers the five ICCES-260 reviewer-response experiments in
`backend/evaluation/` (R1.1, R1.3, R1.4, R1.5, R2.1), cross-checked against
`backend/evaluation/README.md`, `DEBUG_REPORT.md`, `REVIEWER_EVIDENCE_REPORT.md`,
the result JSONs, and the production `backend/app/dmfe` / `backend/app/dmfe/adaptive`
code the scripts claim to exercise. The main IEEE paper draft
(`docs/04_IEEE_Paper_Draft.md`) and `docs/11_ADMFE_Experimental_Evaluation.md`
contain no references to R1.1/R1.3/R1.4/R1.5/R2.1 or to any of these result
files — these five experiments are a self-contained reviewer-rebuttal package,
not (yet) wired into the paper draft's numbers. `results/research_summary.md`,
`results/validation_report.md`, `results/final_metrics_table.md`, and
`results/final_improvement_summary.md` also contain no references to these
five experiments — those docs belong to an earlier/separate evaluation phase.

---

## R1.1

**EXPERIMENT SCRIPT:** `backend/evaluation/robustness_r11.py`

Runs 8 profiles = 2 demand levels (LOW=30, HIGH=120 requests) × 4 temporal
shapes (morning_peak, midday_flat, evening_peak, night_sparse). For each
profile it seeds a fresh isolated SQLite schema, generates requests with the
platform's own `generate_simulation_requests`, then overwrites each
request's `request_timestamp` with a profile-specific offset (a tight burst
for peak shapes, a wide spread for flat/sparse shapes) around a fixed base
date (2026-06-01 06:00 UTC). It then runs `WorkloadRunner.run_pipeline`
(single-pass) followed by up to `MAX_WAVES=25` full-day dispatch waves,
completing trips for real between waves, and records batching rate, average
delay, utilization, distance/fuel/CO2, and a wave-based completion rate.

**RESULT JSON:** `backend/evaluation/results/r11_robustness.json`

Contains all 8 profile results keyed `"<DEMAND>:<profile>"`, each with
`seed`, `requests`, a `single_pass` block (processed/shared/individual
trips, batching_rate_pct, avg_delay_min, avg_utilization_pct,
distance/fuel/CO2) and a `waves` block (waves count, trips_total,
distance/fuel/CO2, requests_completed/failed, completion_rate_pct).
Observed batching_rate_pct ranges from 7.1% (LOW:midday_flat) to 83.3%
(HIGH:morning_peak and HIGH:evening_peak); completion_rate_pct is 100.0 in
all 8 profiles. Also carries `seeds`, `summary` (profile_count=8),
`method_notes`, and a `limitations` field.

**IMPLEMENTATION CROSS-CHECK:** Real production code path, not a
reimplementation. The script imports `framework.py`'s `WorkloadRunner`,
which itself imports and calls `app.dmfe.pipeline.PipelineRunner.run()`,
`app.dmfe.batch_generator.BatchGenerator.create_feasible_batches`,
`app.dmfe.compatibility.CompatibilityCalculator`, `app.dmfe.driver_selection`,
`app.dmfe.optimizer.RouteOptimizer`, and `app.dmfe.adaptive.learning`. I
verified these classes/functions exist with matching signatures in
`backend/app/dmfe/*.py` and `backend/app/dmfe/adaptive/learning.py`
(`class PipelineRunner` / `def run(self, db, limit=200)` in `pipeline.py`;
`class CompatibilityCalculator` / `def compute(...)` in `compatibility.py`;
`class BatchGenerator` / `def create_feasible_batches` in
`batch_generator.py`; `class DriverSelector` / `def select` in
`driver_selection.py`; `class RouteOptimizer` / `def optimize_trip` in
`optimizer.py`; `learning_engine = LearningEngine()` in
`adaptive/learning.py`). `robustness_r11.py` only overwrites the
`request_timestamp` attribute on already-generated `SimulationRequest` rows
before calling the real pipeline — it does not fork or reimplement any
compatibility/scoring/dispatch logic.

**REPRODUCIBILITY:** Fully traceable. `OUT_FILE = os.path.join(RESULTS_DIR,
"r11_robustness.json")` matches the actual result file exactly. Seeds are
hardcoded and deterministic: `SEED_BASE = 1111`, and each profile's seed is
`SEED_BASE + di*100 + ti` (di=demand index, ti=temporal-profile index) —
this reproduces exactly the `seeds` block recorded in the result JSON
(1111–1114, 1211–1214). Each temporal-profile generator function
(`_times_morning_peak`, etc.) uses its own hardcoded `random.Random(999xx)`
seed. The wave loop reseeds `random` and `runner._exec_rng` from
`seed + 1000/9000 + wave_index` per the documented determinism fix (see
`DEBUG_REPORT.md` §5). Running the script as-is should regenerate the same
JSON (only `timestamp` differs) — this is consistent with the file naming
and structure actually present.

**METHODOLOGY:** The script drives the real DMFE dispatch pipeline across
8 synthetic demand/temporal combinations by manipulating only the
`request_timestamp` field that the production time-compatibility gate and
routing logic already read, isolating each run on a fresh SQLite schema so
profiles do not interact, and reports both single-pass and multi-wave
(full-day) aggregate metrics for each combination.

**LIMITATION:** "synthetic robustness sweep" — the requests, demand levels,
and temporal shapes are all synthetically generated by the evaluation
harness's own request generator on a single simulated city (Coimbatore
seed data), not drawn from or validated against real multi-city or
real-world ride/food/parcel demand traces; the script's own
`limitations` field additionally clarifies that `completion_rate_pct`
measures dispatch success (Assigned|Completed), not a finished/completed
trip rate.

**PAPER CLAIM COMPATIBILITY:** `REVIEWER_EVIDENCE_REPORT.md` does not
mention R1.1 at all — it covers only R1.3/R1.4/R1.5/R2.1 (its own roll-up
table lists exactly those four). `README.md` and `DEBUG_REPORT.md` do
describe R1.1, and their numeric claims match the result JSON: README/
DEBUG_REPORT state "HIGH morning/evening peak ≈ 83% vs midday flat 43% /
night sparse 57%; LOW peak ≈ 47–50% vs flat 7% / sparse 11%", which matches
`r11_robustness.json` exactly (HIGH:morning_peak 83.3%, HIGH:evening_peak
83.3%, HIGH:midday_flat 43.3%, HIGH:night_sparse 56.7%; LOW:morning_peak
50.0%, LOW:evening_peak 47.4%, LOW:midday_flat 7.1%, LOW:night_sparse
11.1%). "All profiles dispatch 100%" also matches (all 8
`completion_rate_pct` = 100.0). No discrepancy found for R1.1 — but note
that R1.1 is absent from the "official" reviewer-coverage roll-up document
(`REVIEWER_EVIDENCE_REPORT.md`), which is itself a gap worth flagging (see
Overall Notes).

---

## R1.3

**EXPERIMENT SCRIPT:** two scripts map to R1.3.

1. `backend/evaluation/exact_matching_baseline.py` — compares two
   strategies on the **request-pairing sub-problem only**: (a) "greedy",
   mirroring DMFE's current disjoint-greedy batch selection (sort feasible
   pairs by compatibility score descending, accept if both endpoints
   unmatched), vs (b) "exact", a stdlib-only exact maximum-weight matching
   via subset-DP (`O(2^N·N)`, deliberately capped at `POOL_SIZE=14`). Both
   solvers operate over the identical edge list, where edge weights are the
   real `CompatibilityCalculator.compute([a,b], db)` score for every
   feasible request pair (score ≥ the real `min_compatibility_score`
   threshold read from `SystemConfig`).

2. `backend/evaluation/joint_optimization_baseline.py` (+
   `joint_optimization_worker.py`) — compares DMFE's sequential
   batch-then-route dispatch against a genuinely joint multi-vehicle
   Pickup-and-Delivery model solved in a single OR-Tools pass over the full
   request set (workloads N=50, N=100; vehicle capacity caps 2 and 4). The
   OR-Tools solve runs in an isolated subprocess with a hard wall-clock
   timeout. The script explicitly states this baseline excludes DMFE's
   5-factor compatibility scoring, driver-quality selection, and adaptive
   threshold logic — it isolates only the routing/assignment sub-problem.

**RESULT JSON:**

- `backend/evaluation/results/r13_exact_matching.json` — pool of 14
  requests, threshold=70.0, 91 pairs evaluated, 44 feasible edges. Greedy:
  7 pairs, total_score=611.7. Exact: 7 pairs, total_score=613.1. Relative
  improvement of exact over greedy = +0.23%. Both solvers matched all 14
  nodes (0 unmatched) but chose different pairings for 5 of the 7 pairs.
- `backend/evaluation/results/r13_joint_optimization.json` — for N=50 and
  N=100: DMFE sequential distance (381.20 km / 750.31 km) vs joint cap=2
  (512.39 km / 932.33 km — **worse** than DMFE, −19.8%/−12.3% "saving") vs
  joint cap=4 (382.59 km / 598.39 km). At N=50, cap=4 is ~0.4% better than
  DMFE (1.39 km); at N=100, cap=4 is 20.2% better (−151.92 km). All solves
  report `status: FEASIBLE`, full assignment (0 unassigned).

**IMPLEMENTATION CROSS-CHECK:** Real production code for the scoring/
pairing half. `exact_matching_baseline.py` imports
`app.dmfe.compatibility.CompatibilityCalculator` and `read_float_value`
directly, and computes every pair's score via
`calc.compute([requests[a], requests[b]], db)` — the actual production
scorer, not a reimplementation; only the *selection strategy on top of
those real scores* (greedy vs exact-DP) is written for the experiment.
`joint_optimization_baseline.py` imports `framework.WorkloadRunner` for the
"DMFE sequential" arm, which runs `PipelineRunner.run()` — the real
pipeline. The "joint" arm, however, is **not** DMFE code at all: it is an
independent OR-Tools PDPTW model (`ortools.constraint_solver.pywrapcp`)
built from scratch in `joint_optimization_worker.py`, using only
`haversine` distance and vehicle capacity/mileage pulled from the same
seeded fleet — this is by design an external baseline for comparison, and
the script is explicit that it does not touch DMFE's compatibility scoring
or driver selection.

**REPRODUCIBILITY:** `exact_matching_baseline.py`: `OUT_FILE =
results/r13_exact_matching.json` (matches), `SEED = 1313` hardcoded,
`POOL_SIZE = 14` hardcoded — fully traceable and matches the result JSON's
`"seed": 1313` and `"pool_size": 14`. `joint_optimization_baseline.py`:
`OUT_FILE = results/r13_joint_optimization.json` (matches),
`WORKLOADS = [50, 100]`, `CAPS = [2, 4]`, `seed = 1000 + workload` — matches
the result JSON's `"seed_convention": "seed = 1000 + workload"` and the
per-workload seeds (1050, 1100). The OR-Tools worker subprocess is given
a 30s time limit and the parent enforces a hard subprocess timeout, so
reproducibility of the joint arm depends on OR-Tools' local-search solution
converging to the same optimum within that budget on repeat runs — this is
weaker determinism than the DP/greedy pairing arm, though the script
documents ("Verified deterministic... across re-runs" per
`REVIEWER_EVIDENCE_REPORT.md`) that the observed distances were stable.

**METHODOLOGY:** Two related but distinct comparisons are bundled under
R1.3. The first isolates the *pairing* decision alone: given the same real
compatibility-score graph, does DMFE's greedy disjoint selection lose much
value versus a provably optimal (exact) matching on a small (N=14) pool?
The second isolates the *routing/assignment* decision: given the same
request set and fleet, how much distance does a single joint OR-Tools
optimization save versus DMFE's sequential batch-then-route-one-vehicle
approach, at DMFE's own batch-capacity (cap=2) and at a looser upper-bound
capacity (cap=4)? Both experiments explicitly exclude DMFE's other
decision factors (driver quality, adaptive thresholds) from the baseline
they compare against.

**LIMITATION:** "pairing sub-problem only" — for `exact_matching_baseline.py`
this is stated explicitly and literally (only which two requests get
paired is compared, using the real compatibility score as the sole edge
weight; nothing about vehicle capacity, driver assignment, or route
sequencing is modeled). For `joint_optimization_baseline.py`, "pairing
sub-problem only" is a related but distinct scoping statement — the
comparison there is over the *routing/assignment* sub-problem specifically
(which requests go to which vehicle and in what order), explicitly *not*
including DMFE's compatibility scoring or driver selection; in this
codebase this means the OR-Tools joint baseline is an apples-to-oranges
comparison on distance alone and cannot be read as "OR-Tools beats
A-DMFE" — it shows only that decoupling the batch-formation step from a
single joint vehicle-routing solve can reduce total distance at higher
per-vehicle capacity (cap=4), and can be *worse* than DMFE's own output at
DMFE's actual batch-capacity (cap=2), per the result JSON itself.

**PAPER CLAIM COMPATIBILITY:** Consistent, and notably conservative rather
than overclaiming. `REVIEWER_EVIDENCE_REPORT.md`'s R1.3 section cites
"greedy total 611.7 vs exact optimum 613.1 → +0.23%" (matches
`r13_exact_matching.json` exactly) and the joint table's N=50/N=100
distances (381.20/512.39/382.59 and 750.31/932.33/598.39) match
`r13_joint_optimization.json` exactly, including the −151.92 km (−20.2%)
figure at N=100/cap=4. The doc's own coverage self-assessment ("**85%** —
real joint-optimization evidence with proven savings, but limited to the
routing/assignment sub-problem... The savings are real but bounded to
cap≥4 / larger workloads") is accurate to the data: cap=2 (DMFE's actual
batch size) is *worse* than DMFE in both result rows, and the doc does not
hide this — it states it plainly ("cap=2 is worse because every vehicle
returns to a central depot... disclosed"). No overclaim found.

---

## R1.4

**EXPERIMENT SCRIPT:** `backend/evaluation/per_service_breakdown.py`

Re-aggregates outcomes of the real DMFE pipeline by service type
(`ride`/`food`/`parcel` — exactly `SimulationRequest.request_type`). For a
set of workloads it runs `WorkloadRunner.run_pipeline` (single-pass) +
`run_waves` (full-day), then walks the resulting `Trip` rows, attributes
each trip to its dominant (most-frequent) service among its constituent
request ids, and computes per-service requests/dispatched/shared/
individual/batching-rate/distance/fuel/utilization/delay, with an explicit
reconciliation check (`per_service` sums must equal `overall` totals; the
script raises `RuntimeError` and refuses to write if they don't).

**RESULT JSON:** `backend/evaluation/results/r14_per_service.json`

Contains a **single** workload run: `seed: 1404`, 60 total requests (ride
24 / food 24 / parcel 12), `overall` block (60 dispatched, 100%
assignment, 35 trips, 22 shared, batching_rate_pct 62.9%), and a
`per_service` block with ride (batching 73.7%, 19 trips), food (batching
53.8%, 13 trips), parcel (batching 33.3%, 3 trips). `reconciliation.reconciled:
true`.

**IMPLEMENTATION CROSS-CHECK:** Real production code path — the script
imports and uses `framework.WorkloadRunner`, which calls the real
`PipelineRunner.run()`, `BatchGenerator`, `CompatibilityCalculator`, etc.
(same chain verified for R1.1 above). `per_service_breakdown.py` adds no
new dispatch/scoring logic of its own; it only re-groups already-dispatched
`Trip`/`SimulationRequest` rows by `request_type` after the real pipeline
has run. This is honestly and accurately what the docstring claims: "then
re-aggregates the stored results by service type" — it is a **post-hoc
breakdown of an existing metric (batching rate / dispatch outcome), sliced
by service type**, not a new capability or a new metric. It does not test
whether DMFE treats the three service types differently in its scoring
logic — it only reports how the existing pipeline's aggregate outcomes
happen to differ by service, given the request mix generated.

**REPRODUCIBILITY — SIGNIFICANT FINDING:** The script currently on disk
does **not** reproduce the result JSON currently on disk. The script's
`main()` defines `WORKLOADS: List[int] = [50, 100, 250, 500]`,
`OUT_FILE = os.path.join(RESULTS_DIR, "r14_per_service_all.json")`, and
loops over all four workloads with `seed = 1000 + workload`, writing a
top-level `"results": {"50": {...}, "100": {...}, "250": {...}, "500":
{...}}` structure. The actual file present,
`results/r14_per_service.json`, has a different filename, a different
top-level shape (flat — `workload`, `overall`, `per_service` at the top
level, no `"results"` wrapper), a single workload of N=60 (not one of
50/100/250/500), and `seed: 1404` (not `1000+60=1060`, which is what the
current script's seed convention would produce for N=60 if 60 were even in
its `WORKLOADS` list — it is not). Running `per_service_breakdown.py` as it
exists today would **not** regenerate `r14_per_service.json`; it would
produce a differently-named, differently-shaped, differently-workloaded
file that does not currently exist anywhere in the repository (confirmed
by `find -iname "*r14*"`, which returns only the existing single-workload
JSON). `README.md`'s file listing (`results/r14_per_service.json`) and
`DEBUG_REPORT.md`'s R1.4 numbers (ride 24/food 24/parcel 12, overall
batching 62.9%) match the *result file that exists*, not the script that
currently produces it — meaning the script has been edited to a broader,
multi-workload design at some point after the shipped result file and
README/DEBUG_REPORT text were finalized, and has evidently not been re-run
since.

**METHODOLOGY:** As shipped (single N=60 run), the experiment runs one
deterministic 60-request workload through the real dispatch pipeline,
groups the resulting trips by dominant service type, and reports batching
rate, distance, fuel, utilization and delay per service, verifying that
the per-service sums reconcile to the overall totals. This is a per-service
breakdown of one already-existing pipeline metric (batching/dispatch
outcome), not an independent new experiment or a claim about
service-differentiated logic inside DMFE.

**LIMITATION:** The result JSON reflects **one deterministic workload**
(N=60, seed 1404), not the multi-workload sweep (N=50/100/250/500) that
the current script is written to produce and that
`REVIEWER_EVIDENCE_REPORT.md` reports as if it exists. `per_service_breakdown.py`
is a re-aggregation of an existing pipeline output (batching rate /
dispatch counts) by service label, using synthetic requests generated by
the harness's own generator — it is not a measure of real-world per-service
demand or behavior, and the per-service split intentionally omits fuel/CO2
per-service allocation because a shared trip has no principled per-leg
cost split (stated directly in the script's own `limitations` field).

**PAPER CLAIM COMPATIBILITY — MISMATCH FOUND.**
`REVIEWER_EVIDENCE_REPORT.md`'s R1.4 section presents a four-row table
(N=50/100/250/500) with specific per-service batching percentages (e.g.
"N=500: 261 (238) trips, 91.2% overall, ride 92.2% / food 88.9% / parcel
92.3%") and cites `results/r14_per_service_all.json` as the evidence file.
**Neither that file nor any data supporting those N=50/100/250/500 numbers
exists anywhere in the repository** — only the single N=60 result
(`r14_per_service.json`, overall batching 62.9%) is present. This means the
headline claim actually asserted in the reviewer-response document ("DMFE
achieves high batch coverage, and it holds (and grows) across all three
service types and across workload sizes," with a monotonic-growth table
62.9%→91.2%) is **not currently backed by any artifact in this
repository** — it cannot be verified, and the only artifact that *is*
present (a single N=60 run at 62.9% batching) does not by itself support a
claim about growth across workload sizes. This is a genuine
paper/report-vs-evidence gap, not a rounding or wording nuance, and should
be treated as the most material finding of this audit: either the
multi-workload run needs to be re-executed and the resulting
`r14_per_service_all.json` committed, or the reviewer-response document's
table and claim need to be retracted/rewritten to describe only the single
N=60 evidence actually on disk. Separately, small numeric drift also
exists between `DEBUG_REPORT.md`'s R1.4 figures (ride 68.4%, parcel 25.0%)
and the batching_rate_pct fields actually in `r14_per_service.json` (ride
73.7%, parcel 33.3%) — overall (62.9%) and food (53.8%) match exactly, but
the ride/parcel per-service figures in DEBUG_REPORT.md do not match the
shipped JSON's trip-based batching_rate_pct field, suggesting DEBUG_REPORT.md
was drafted from a different metric definition or a different run than the
one ultimately committed.

---

## R1.5

**EXPERIMENT SCRIPT:** `backend/evaluation/acceptance_r15.py`

Explicitly documented as "A SIMULATION — NOT A HUMAN STUDY" in its own
module docstring. Because DMFE's real pipeline dispatches every request it
can serve (yielding a trivial, uninformative 100% "acceptance"), the script
instead applies a **post-hoc compatibility-score cutoff** to the set of
already-dispatched requests: `accepted(request, cutoff) = dispatched(request)
AND best_compatibility_score(request) >= cutoff`, where the score is the
real batch `compatibility_score` for shared trips and 0.0 for
solo/individual trips (which therefore fail any cutoff > 0). It runs 5
repeats (`REPEATS = 5`, seeds 1515–1519) of a 60-request workload through
the real pipeline (single-pass + full-day waves), sweeps cutoffs
[0,30,50,60,70,75,80,85,90], and additionally computes a per-priority
(Low/Medium/High) acceptance rate and a priority-weighted acceptance figure
at the engine's own real threshold (70).

**RESULT JSON:** `backend/evaluation/results/r15_acceptance.json`

5 per-seed runs plus an `aggregate` block. At cutoff=0 (unselective),
mean acceptance = 100.0% across all 5 repeats — matches the trivial-case
claim. At cutoff=70 (DMFE's own real `min_compatibility_score`/headline
threshold), mean acceptance = 81.3% (min 68.3%, max 90.0% across the 5
seeds). Acceptance falls monotonically per-repeat as the cutoff rises to
90 (mean 31.3%). `priority_weighted_acceptance_at70_pct` mean = 81.0%
(min 65.5%, max 94.7%).

**IMPLEMENTATION CROSS-CHECK:** Real production code for both the dispatch
and the score used in the gate. The script imports
`framework.WorkloadRunner` (real `PipelineRunner.run()` per the same chain
verified above) and `app.dmfe.models.DMFEBatch`, reading each dispatched
`Trip`'s real batch (`trip.batch.compatibility_score`) — the actual
persisted production compatibility score, not a recomputation or
simplified proxy. The acceptance *cutoff* logic itself
(`_best_scores_by_request`, `acc_count`) is new code written for the
experiment, but it is applied as a filter on top of real dispatch/scoring
outputs, not a reimplementation of the dispatch or scoring engine.

**REPRODUCIBILITY:** Fully consistent — `OUT_FILE =
os.path.join(RESULTS_DIR, "r15_acceptance.json")` matches the actual
result file exactly, unlike R1.4/R2.1. `SEED_BASE = 1515`, `REPEATS = 5`,
`WORKLOAD = 60`, `CUTOFFS = [0,30,50,60,70,75,80,85,90]` are all hardcoded
and match the JSON's `seed_base`, `repeats`, `workload`, and `cutoffs`
fields exactly, as do the seeds used for each run (1515–1519, i.e.
`SEED_BASE + i` for i in range(5)) and the wave-phase reseeding fix
(`random.seed(seed + 1000 + waves)` / `runner._exec_rng =
random.Random(seed + 9000 + waves)`), consistent with the determinism fix
documented in `DEBUG_REPORT.md` §5.

**METHODOLOGY:** The experiment runs 5 independent deterministic 60-request
workloads through the real dispatch pipeline (which always dispatches
every servable request), then reinterprets "acceptance" as passing a
configurable post-hoc compatibility-score cutoff applied to the score each
request's assigned trip actually achieved, so that the headline figure
reflects how many dispatched requests met the engine's own real
70-point quality bar rather than being dispatched via a solo/fallback
trip with no compatible partner found.

**LIMITATION:** "simulation, not human study" — every acceptance number
in this experiment is a *modeling assumption imposed on the real dispatch
output* (a chosen score cutoff = "accepted"), not an observed or measured
preference, choice, or behavior from any real rider, driver, or requester;
the 100% "dispatched" baseline also assumes unlimited fleet capacity over
the simulated day, which the script's own `limitations` field flags as
something that would be lower under real capacity pressure.

**PAPER CLAIM COMPATIBILITY:** Consistent. `REVIEWER_EVIDENCE_REPORT.md`'s
R1.5 table (cutoff row: 100.0/81.3/81.3/81.3/**81.3**/69.3/57.7/49.4/31.3)
matches `r15_acceptance.json`'s `aggregate.compatibility_cutoff_sweep`
mean values exactly at every cutoff point, and the stated headline
("81.3% at DMFE's own compatibility threshold (70) — not 100%") matches
`aggregate.headline_acceptance_at_threshold70_pct.mean = 81.3`. The doc's
self-assessed coverage ("80% — a real, executed acceptance analysis... but
it is an assumed post-hoc threshold model... and takes an
unlimited-capacity baseline") is an accurate, non-overclaiming
characterization of what the data shows.

---

## R2.1

**EXPERIMENT SCRIPT:** `backend/evaluation/time_window_sensitivity_r21.py`

Sweeps `SystemConfig.max_allowed_delay_min` — described in the script's
own docstring as "the DMFE time-window constraint that the CURRENT
implementation actually consumes" — over values [10, 15, 20, 25, 30]
minutes, at two workload sizes (N=50, N=100, per `WORKLOADS = [50, 100]`
and `SEED_FOR = {50: 2121, 100: 2122}`). For each sweep point it reseeds
`SystemConfig` with the new value, calls the project's own
`clear_config_cache()` (config is TTL-cached), regenerates the same
deterministic request set for that workload, runs the real pipeline
(single-pass + full-day waves), and — importantly — reads the value back
via `read_float_value(db, DELAY_KEY, 20.0)` to prove the knob actually took
effect end-to-end rather than being silently ignored by a cache.

**RESULT JSON:** `backend/evaluation/results/r21_time_window.json`

Contains a **single** `seed: 2121` and a `points` dict keyed by sweep
value (10/15/20/25/30), each showing `requests: 60` (not 50 or 100),
`delay_budget_seen_by_engine_min` equal to the sweep value at every point,
and `knob_took_effect: true` for all 5 points
(`all_knob_values_took_effect: true`). Batching rate rises from 55.6% (W=10)
to 69.7% (W=20), then plateaus at 69.7% for W=25 and W=30 — the W=25 and
W=30 rows are numerically identical (batching_rate_pct, distance, fuel all
match exactly between the two).

**IMPLEMENTATION CROSS-CHECK:** Real production code path. The script
imports `app.dmfe.compatibility.clear_config_cache` and `read_float_value`
directly (both confirmed present in `backend/app/dmfe/compatibility.py`:
`def clear_config_cache()` and `def read_float_value(db, key, default)`),
and drives dispatch through `framework.WorkloadRunner` → the real
`PipelineRunner.run()`. I confirmed `max_allowed_delay_min` is read by
production code in 9 files including `batch_generator.py`,
`compatibility.py`, `optimizer.py`, `pipeline.py`, and
`adaptive/decision.py`/`adaptive/factors.py`/`adaptive/matrix.py` — this
is a genuinely load-bearing, widely-consumed config key, not a decorative
one. I also confirmed the script's claim that `SimulationRequest
.max_acceptable_delay_min` exists in the schema (`app/db/models.py`) but is
never read anywhere else in the codebase besides that model definition and
this script's own docstring — supporting the claim that no fake
per-request time-window column was substituted.

**REPRODUCIBILITY — SIGNIFICANT FINDING (same pattern as R1.4):** The
script currently on disk does **not** reproduce the result file currently
on disk. `time_window_sensitivity_r21.py`'s `main()` loops over
`WORKLOADS = [50, 100]` and writes `OUT_FILE = os.path.join(RESULTS_DIR,
"r21_time_window_all.json")`, with a top-level `"workloads": [50, 100]`
and `"results": {"50": {...}, "100": {...}}` structure (one sweep of 5
points per workload, seeded 2121 and 2122 respectively). The actual file
present, `results/r21_time_window.json`, has a different filename, a flat
`"points": {...}` structure (no per-workload nesting), a single `"seed":
2121`, and every point shows `"requests": 60` — not 50 or 100 as the
current script's `WORKLOADS` list would produce. Running the current
script would not regenerate this file; it would produce a differently
named, differently shaped, two-workload file
(`r21_time_window_all.json`) that, like `r14_per_service_all.json`, does
not exist anywhere in the repository (confirmed via `find -iname "*r21*"`,
which returns only the existing single-run JSON). As with R1.4,
`README.md`'s file listing and `DEBUG_REPORT.md`'s R2.1 figures ("~56% @10
min → ~65% @15 min → ~70% @20–30 min") match the single N=60 file that
exists, not the N=50/N=100 sweep the current script is written to
produce — indicating the same pattern of the script being broadened after
the shipped result and docs were finalized, without a corresponding re-run.

**METHODOLOGY:** As shipped (single N=60, seed 2121 run), the experiment
holds the request set and fleet fixed across five sweep points and varies
only the real `max_allowed_delay_min` configuration value, verifying via a
read-back that the pipeline's cache genuinely picked up each new value,
and reports how batching rate, distance, fuel, and average delay respond —
establishing that this specific config knob is both real (production code
reads it in multiple modules) and functionally load-bearing (it visibly
changes dispatch outcomes) rather than an inert one.

**LIMITATION:** "max_allowed_delay_min configuration sweep" — the only
independent variable varied here is a single global `SystemConfig` value;
this is a configuration/hyperparameter sensitivity sweep of one existing
knob, not a test of DMFE's behavior under varying real-world delay
tolerances at the individual-request level (the schema's per-request
`max_acceptable_delay_min` field exists but is confirmed unused by the
engine), and — as with R1.1 — completion/dispatch figures reflect
unlimited-wave dispatch, not necessarily a single-pass operational
snapshot.

**PAPER CLAIM COMPATIBILITY — MISMATCH FOUND.**
`REVIEWER_EVIDENCE_REPORT.md`'s R2.1 section presents a two-row table
(N=50, N=100) with specific batching percentages at each of the five sweep
points (e.g. "N=100: W=10 60.0%, ..., W=30 76.4%") and cites
`results/r21_time_window_all.json` as the evidence file. **Neither that
file nor any data supporting the claimed N=50/N=100 breakdown exists
anywhere in the repository** — only the single N=60 result
(`r21_time_window.json`, batching 55.6%→69.7% across W=10→30) is present.
The reviewer-response document's specific numeric claims (e.g. "N=50
plateaus at 70.4% from W=20; N=100 monotonic 60.0%→76.4%") cannot be
verified against any artifact currently in this repository. This is the
same class of finding as R1.4 and should be treated with equal weight:
either the two-workload sweep needs to be re-executed and
`r21_time_window_all.json` committed, or the claim in
`REVIEWER_EVIDENCE_REPORT.md` needs to be scoped down to the single N=60
run that is actually present and verifiable.

---

## Overall Reviewer-Readiness Notes (qualitative only)

**What is solid.** All five scripts genuinely exercise the real DMFE/
A-DMFE production code path (`PipelineRunner`, `BatchGenerator`,
`CompatibilityCalculator`, `DriverSelector`, `RouteOptimizer`,
`adaptive.learning`) through the shared `framework.py` harness — this was
verified by reading the actual import statements and confirming the
imported classes/functions exist with matching signatures in
`backend/app/dmfe/`. None of the five scripts reimplement DMFE's
compatibility scoring, batching, or dispatch logic; where a script adds
its own algorithm (the exact-matching DP in R1.3, the OR-Tools joint model
in R1.3, the acceptance-cutoff filter in R1.5), it is applied strictly as
a post-hoc analysis or an external baseline on top of the real engine's
outputs or real engine's scores, and every script is explicit in its own
docstring and `limitations` field about exactly what it does and does not
claim. R1.3 and R1.5 in particular are honest to the point of
self-undermining their own best-case story (R1.3 discloses that the joint
baseline is *worse* than DMFE at DMFE's actual batch capacity; R1.5 leads
with the sub-100% "real" headline instead of the trivial 100% figure).
R1.1 and R1.5 have the strongest reproducibility guarantee found in this
audit: their scripts' `OUT_FILE` paths, hardcoded seeds, and documented
logic match the shipped result JSONs exactly.

**What needs attention before reviewer submission.** Two of the five
experiments (R1.4, R1.5's sibling R2.1) have a script/result mismatch that
a careful reviewer or examiner could catch: the scripts currently in the
repository (`per_service_breakdown.py`, `time_window_sensitivity_r21.py`)
are written to sweep multiple workloads and write to `*_all.json` output
files, but the result files actually committed
(`r14_per_service.json`, `r21_time_window.json`) are single-workload runs
under different filenames with different structures — and
`REVIEWER_EVIDENCE_REPORT.md`'s headline tables for R1.4 and R2.1 cite
numbers (multi-workload batching-rate growth to 91.2% for R1.4; a
per-workload W=10→30 sweep table for R2.1) that do not correspond to any
data file present anywhere in this repository. This is not a matter of
interpretation or wording — it is a literal absence of the underlying
evidence file for two of the four claims in the document that exists
specifically to answer reviewers. Before this material goes to
reviewers/examiners, either (a) the multi-workload versions of both
scripts should be re-run and their `_all.json` outputs committed so the
tables in `REVIEWER_EVIDENCE_REPORT.md` are backed by real files, or (b)
the tables and claims in that document should be rewritten to describe
only the single-workload evidence that is actually present
(`r14_per_service.json` at N=60, batching 62.9%; `r21_time_window.json` at
N=60, batching 55.6%→69.7%). Doing neither and submitting the document as-is
would mean presenting numbers to reviewers that cannot currently be traced
to any artifact in the codebase.

**A secondary, smaller gap.** `REVIEWER_EVIDENCE_REPORT.md` — the document
whose explicit purpose is to roll up coverage for the reviewer
experiments — covers only four of the five (R1.3, R1.4, R1.5, R2.1) and
omits R1.1 entirely from its roll-up table, even though R1.1's own script
and result JSON are complete, internally consistent, and correctly
described in `README.md`/`DEBUG_REPORT.md`. This looks like an omission
rather than a quality problem with R1.1 itself, but it means the "coverage"
document a reviewer would be handed does not currently mention one of the
five points this audit was asked to verify.

**Consistency of "no fabrication" claims.** Every script includes an
explicit "abort rather than fabricate" guard (e.g. `raise RuntimeError` if
`generate_simulation_requests` returns fewer rows than requested, or if
per-service/per-workload reconciliation fails), and the results that are
present carry `reconciled: true` / matching totals wherever such checks
exist. This pattern was consistent across all five scripts read for this
audit and is a genuine strength worth keeping intact.
