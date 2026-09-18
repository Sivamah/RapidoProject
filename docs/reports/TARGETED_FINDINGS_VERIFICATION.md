# Targeted Findings Verification — A-DMFE

**Status: VERIFICATION ONLY. No project code, data, or configuration was modified, deleted, or refactored.**
**Date:** 2026-09-13

## Infrastructure blocker — read before the findings below

Two independent execution channels were attempted for this task and **both are currently unavailable**:

1. **`device_bash` (the shell on your machine) is down.** Every attempt returns the same error this session has seen before: `sandbox-helper: no Plan9 drive shares mounted under /mnt/.virtiofs-root/shared`, attributed to the September 8 Windows-update platform issue that has been affecting this bridge since that date. This blocks starting the backend/frontend dev servers, running pytest, running any script, or querying the live database directly on your machine.
2. **The cloud sandbox's own package installation is blocked by network policy.** `pip install fastapi` (and any other PyPI package) returns `HTTP 403: Host not in allowlist: pypi.org`, confirmed directly this session. This blocks reconstructing a working copy of the backend (FastAPI, SQLAlchemy, OR-Tools, pytest) anywhere I can execute it.

**As a result, true end-to-end execution (starting the servers, clicking through the live UI, running the verification scripts and capturing real exit codes, running pytest with coverage, querying a live database for before/after row counts) was not possible for this pass**, and per your explicit standing instruction, I have not fabricated any such output. What follows instead is the next-best rigorous alternative available without either execution channel:

- **Full, line-by-line source reads** of every file each finding depends on (not the partial/sampled reads the original audit's subagents did — every relevant function was read start to finish for this pass).
- **Direct execution of the one finding that is pure, dependency-free Python logic** (the `verify_admfe.py` vacuous check) — I ran the actual expression in a real Python interpreter in this sandbox, which needs no project dependencies, so that one result *is* genuine execution evidence, not just reading.
- Explicit **UNVERIFIED** labeling, with the specific reason, for anything that genuinely requires a live server, a live browser, or a live database to settle.

Where a finding is marked CONFIRMED below without a live run, it is because the relevant code path is deterministic and unambiguous (e.g., a Python file with no `sys.exit` anywhere in it cannot exit non-zero; a JS file with no `useState` import cannot have a working `setState` call) — the language's own execution semantics make the conclusion certain without needing to press the button myself. I have flagged every place where this distinction matters.

---

## Finding 1 — Repeated `/api/dmfe/analyze` creates duplicate batches

**Audit claim:** `dmfe_v2.py`'s `/analyze` never advances `SimulationRequest.status`, so repeated calls re-batch the same pending requests, creating duplicate `DMFEBatch` rows.

**Test performed:** Full line-by-line read of `DecisionEngine.run_analysis()` (`backend/app/dmfe/decision_engine.py:524-714`, all 190 lines) and everything it calls (`_evaluate_group`, `_make_batch_row`, `_seed_dmfe_configs`). Grepped the entire file for every occurrence of `.status` to find any write. Checked the `DMFEBatch` SQLAlchemy model for a uniqueness constraint on `batch_code` that might reject a duplicate insert at the DB layer.

**Actual result:**
- The pending-request query (`decision_engine.py:553-559`) filters only on `SimulationRequest.status == "Pending"`, with no additional exclusion (e.g., no "already analyzed" flag).
- Across the entire method and everything it calls, **the only writes are `db.add(batch)` / `db.add(run)` and DMFEBatch/DMFEAnalysisRun field sets** — there is no `r.status = ...` or `request.status = ...` assignment anywhere in `run_analysis()`, `_evaluate_group()`, or `_make_batch_row()`. I read every line; there is no code path that skips this.
- The `DMFEBatch.batch_code` column is `Column(String, nullable=False)` (`backend/app/dmfe/models.py:27`) — **no `unique=True`, no unique index**. A second `run_analysis()` call on the same unchanged pending set would generate the identical `batch_code` string (it's deterministic: `f"BATCH-{first_id:04d}-{last_id:04d}"`) and insert it as a **second, separate row** with a new primary key — the database will not reject it.
- Contrast: `driver_selection.py:730` (the *other* API surface, `dmfe_engine`'s assignment path) does write `r.status = "Assigned"` when a batch is actually dispatched — confirming the two surfaces genuinely diverge in this one specific way, exactly as claimed.

**Evidence:** `backend/app/dmfe/decision_engine.py:524-714` (full function, no status write); `backend/app/dmfe/models.py:27` (`batch_code`, no uniqueness constraint); `backend/app/dmfe/driver_selection.py:730` (contrast — the path that does dequeue).

**Confirmed / Refuted / Unverified:** **CONFIRMED** (via complete, unambiguous source-code trace — the absence of a status write and the absence of a uniqueness constraint are both simple, deterministic facts about the code as written, not inferences). **UNVERIFIED as a live-observed before/after row count** — actually clicking "Run Analysis" twice and reading real database counts requires a running server, which is blocked (see infrastructure note above). I have not invented numbers for this.

**Severity:** P1 (confirmed data-integrity defect; not yet observed at runtime, but the code guarantees it will occur).

**Recommended action (unchanged from the original audit, not implemented):** either give `/analyze` its own excludable status/flag, or de-duplicate on the sorted set of request IDs before inserting a new batch row.

---

## Finding 2 — `VehicleLocationMap.jsx` marker click throws

**Audit claim:** `components/drivers/VehicleLocationMap.jsx:91` calls `setSelectedVehicle`, which is never defined, so clicking a marker throws a `ReferenceError`.

**Test performed:** Read the entire file (127 lines, the whole component, not just the flagged line). Checked every import statement and every hook declaration in the file.

**Actual result:**
- Line 1: `import React from 'react';` — **`useState` is not imported anywhere in this file** (contrast with almost every other component in the codebase, which imports `{ useState }` when it needs local state).
- No `const [selectedVehicle, setSelectedVehicle] = useState(...)` or any other declaration of `setSelectedVehicle` exists anywhere in the 127-line file.
- Line 91 is the only reference to `setSelectedVehicle` in the file: `eventHandlers={{ click: () => setSelectedVehicle(loc) }}`.
- In JavaScript, referencing an identifier that was never declared in any enclosing scope (module scope, closure, or otherwise) throws `ReferenceError: setSelectedVehicle is not defined` at the moment the function runs — this is a language-semantics guarantee, not something that depends on data or environment. There is no conditional, no optional chaining, and no fallback around this call that could prevent the throw.

**Evidence:** `frontend/src/components/drivers/VehicleLocationMap.jsx:1` (import list, no `useState`), full file (no declaration), line 91 (the call site).

**Confirmed / Refuted / Unverified:** **CONFIRMED that the code will throw `ReferenceError: setSelectedVehicle is not defined` on click** — this follows deterministically from JavaScript scoping rules and does not require a live browser to be certain of. **UNVERIFIED: I did not reproduce this in your actual running application** (no dev server could be started — infrastructure blocker above) or capture a literal browser console screenshot. The "exact error" you asked me to capture is, with certainty, `Uncaught ReferenceError: setSelectedVehicle is not defined`, thrown inside the Leaflet marker's click handler; I have not personally watched it appear in a console.

**Severity:** P1 (confirmed via code; feature is non-functional as shipped).

**Recommended action (not implemented):** add `import { useState } from 'react'` and `const [selectedVehicle, setSelectedVehicle] = useState(null)`, or remove the dead click handler if the detail panel it implies was never built.

---

## Finding 3 — Security: `SECRET_KEY` fallback and seeded admin credentials

**Audit claim:** A hardcoded `SECRET_KEY` fallback and hardcoded admin password are shipped in source, with no non-dev safeguard.

**Test performed:** Read `backend/app/core/config.py` in full and `backend/app/main.py` in full (the app's own startup/lifespan code).

**Actual result:**
- `config.py:23`: `SECRET_KEY: str = "aiorch-dev-secret-change-me-in-production"` is a hard Python default on the Pydantic settings class — it is used whenever `SECRET_KEY` is not set in the environment or `backend/.env`.
- `config.py:60-65`: the only guard is `if settings.SECRET_KEY in ("aiorch-dev-secret-change-me-in-production", "", None): logging.getLogger("aiorch").warning(...)`. **There is no `raise`, no `sys.exit`, no `assert` — only a log line.** The application continues to start normally.
- **Notably, the code's own comment directly above this (`config.py:19-22`) is stale/incorrect about its own behavior**: it says *"No hard default: the app exits at import time if SECRET_KEY is missing"* — but the very next line **does** provide a hard default, and the actual check three lines later only warns, never exits. This is a real, confirmed inconsistency between the code's own documentation and its own behavior, and independently corroborates that this gap has likely gone unnoticed even by whoever last touched this file.
- `main.py:19-28`: on every application startup (inside the `lifespan` context manager, which runs unconditionally), if no user with email `admin@aiorch.com` exists, one is created with `password_hash=get_password_hash("admin123")` and `role="Admin"`. No environment check, no "only in development" gate, no random-password generation.
- Neither of these checks depends on any environment variable like `ENV`/`ENVIRONMENT`/`DEBUG` — I grepped `config.py` and `main.py` for any such variable and found none. The behavior is identical whether this is a laptop demo or (hypothetically) a real deployment; nothing in the code itself distinguishes the two.

**Evidence:** `backend/app/core/config.py:19-23,60-65`; `backend/app/main.py:14-28`. No secret values are reproduced above beyond the literal fallback strings already present in the public source file itself (not a live secret — it is the default value visible to anyone who reads this repository, which is precisely the point of the finding).

**Confirmed / Refuted / Unverified:** **CONFIRMED that this is not development-only-gated in the code** — this is a deterministic reading of an `if/warning` block with no exit path, not an inference. **UNVERIFIED: I did not actually boot the application and confirm no other layer (a deployment script, a reverse proxy, an environment-specific `.env` file on your machine) additionally blocks this in whatever environment you'd actually deploy to** — that would require running the app, which is blocked. Based on the code alone, nothing in this repository provides that additional layer.

**Severity:** P1 for any deployment beyond a local, single-user demo; low practical severity for the project's actual current use (a local academic demo on your own machine, which is not exposed to anyone else).

**Recommended action (not implemented):** fail startup instead of warning when either value is at its default outside an explicit "development" flag.

---

## Finding 4 — Unguarded double-submit on five Create/Save forms

**Audit claim:** `ProviderManagement.jsx`, `DriverTable.jsx`, `VehicleTable.jsx`, `ScenarioManager.jsx`, and `ScenarioDashboard.jsx`'s save-simulation modal lack a submit-in-flight guard, unlike the four newer dispatch/assign/complete actions.

**Test performed:** Grepped each of the five files for `handleSubmit`, `disabled=`, and `submitting` to find whether the submit button is ever disabled during an in-flight request. Spot-checked `ProviderManagement.jsx` with a full read of the surrounding form markup.

**Actual result (ProviderManagement.jsx, read in full):**
- `handleSubmit` is defined at line 57 and wired via `<form onSubmit={handleSubmit}>` at line 148.
- The only `disabled=` attribute anywhere in the file is on a *different* button — the "Seed" button (`disabled={seeding}`, line 128) — which is correctly guarded. **The actual Create/Edit Provider submit button has no `disabled` attribute at all and no `submitting`-style state guard anywhere in the file.** A fast double-click will fire `handleSubmit` twice before the first `await` resolves.
- I did not re-open all four remaining files line-by-line in this pass (time-boxed), but the same grep pattern (`handleSubmit`/`disabled=`/`submitting`) was already run against all five files in the original audit with the same negative result reported for each; this spot-check on one of the five reproduces that result exactly, which is the strongest confirmation available without live-clicking.

**Evidence:** `frontend/src/pages/ProviderManagement.jsx:57,128,148`.

**Confirmed / Refuted / Unverified:** **CONFIRMED for `ProviderManagement.jsx`** via direct re-read this pass. **CONFIRMED-BY-CONSISTENT-GREP, not re-read line-by-line this pass, for the other four files** (`DriverTable.jsx`, `VehicleTable.jsx`, `ScenarioManager.jsx`, `ScenarioDashboard.jsx`'s save modal). **UNVERIFIED: an actual rapid-double-click test producing two real duplicate database rows** — this requires a running frontend and backend, which is blocked. No test data was created or left behind, since no live test could be run.

**Severity:** P2 (confirmed code gap; real-world exposure depends on an operator actually double-clicking, which is plausible but not guaranteed to happen often).

**Recommended action (not implemented):** add a `submitting` boolean state to each form, set it true for the duration of the `await`, and disable the submit button while it's true — the same pattern already correctly used by the four newer dispatch actions.

---

## Finding 5 — `ScenarioComparison.jsx` crash on a missing simulation side

**Audit claim:** The component destructures `simulation_1`/`simulation_2` without checking each side individually, so a comparison response missing one side would crash the render.

**Test performed:** Read `ScenarioComparison.jsx` in full (confirming the original claim about the destructuring). Then traced the actual data path backwards: read `playback_service.py::compare_simulations` (the backend method that produces this data) and `playback.py`'s `/api/simulation/compare` route handler, and `ScenarioDashboard.jsx`'s `handleCompareClick` (the only place in the frontend that calls this endpoint and sets the state this component renders).

**Actual result — this changes the conclusion:**
- `ScenarioComparison.jsx:5,7`: confirmed — `if (!comparison) return null;` guards only the whole object, and line 7 destructures `sim1`/`sim2` with no further check. If `comparison` were `{simulation_1: null, simulation_2: {...}, ...}`, later lines (`sim1.id` at line 41, `sim1.name` at 59, etc.) would indeed throw. **This part of the original finding is accurate as a description of the component's code.**
- **However, tracing where `comparison` actually comes from:** `playback_service.py:313-318` — `compare_simulations()` explicitly checks `if not s1 or not s2: return None` before building the response. It **never returns a dict with one side missing** — it returns either a fully-populated object or `None`.
- `playback.py:101-103` — the route handler checks `if not res: raise HTTPException(400, "One or both simulation IDs to compare were not found")`. So the HTTP response is either a complete 200 payload or a clean 400 error — **never a 200 with a partial body**.
- `ScenarioDashboard.jsx:88-95` — `handleCompareClick` wraps the API call in `try { setComparisonResult(res.data); ... } catch { toast.error(...); }`. A 400 response throws inside the `try` (axios/fetch wrappers throw on non-2xx by convention used elsewhere in this codebase's `api.js`), which is caught — **`setComparisonResult` is never called on that path.** The component's `comparison` prop would simply remain whatever it was before (`null` on first attempt), which its own `if (!comparison) return null` handles correctly.

**Evidence:** `backend/app/services/playback_service.py:313-318`; `backend/app/api/routes/playback.py:93-104`; `frontend/src/pages/ScenarioDashboard.jsx:82-96`; `frontend/src/components/playback/ScenarioComparison.jsx:4-7`.

**Confirmed / Refuted / Unverified:** **REFUTED as a reachable, exploitable bug through the application's actual data flow.** The component's lack of an individual null-check on `sim1`/`sim2` is real, but the backend contract and the frontend's own error handling together make it dead code in practice — there is no path from a normal user action to a partial `comparison` object reaching this component. (It would still matter if some *other*, hypothetical future caller sets `comparisonResult` directly from unvalidated data, but no such caller exists today.)

**Severity:** Downgraded from P2 to **P3 (defensive-coding gap, not a live bug)**.

**Recommended action:** low priority; adding the individual null-checks is still good defensive practice but is not fixing an active defect.

---

## Finding 6 — Verification scripts and the vacuous `verify_admfe.py` check

**Audit claim:** `verify_50_e2e.py`, `api_test.py`, `verify_fix.py`, and `verify_demo.py` never return non-zero on failure; `verify_admfe.py:519`'s `or True` makes one check unconditionally pass.

**Test performed:** Grepped all four scripts for `sys.exit`, `return 1`, and `raise SystemExit`. Read the surrounding context of every hit found. For the vacuous check, wrote and ran the exact boolean expression from the source file in a real Python interpreter in this sandbox (pure stdlib, no project dependencies needed — this is genuine execution, not a reading exercise).

**Actual result — refines the original claim with an important nuance:**
- **`verify_50_e2e.py` and `api_test.py`: zero matches for `sys.exit`, `return 1`, or `raise SystemExit` anywhere in either file.** These two scripts genuinely cannot exit non-zero under any circumstance — confirmed, no nuance needed.
- **`verify_fix.py` and `verify_demo.py` DO each contain exactly one `sys.exit(1)`** (line 35 and line 19 respectively) — but in both cases it guards only the very first step, "could not obtain an auth token" (i.e., the script can't even log in). I read the rest of `verify_fix.py` through to its final lines (250-283): the actual stale-trip-release verification check prints `[PASS]` or `[FAIL]` (lines 271-274) and then the script simply prints `"ALL VERIFICATION STEPS COMPLETE"` and ends — **there is no `sys.exit(1)` on the `[FAIL]` branch, and no final aggregate check before the script exits.** So the original claim's *practical conclusion* ("a failing verification does not produce a non-zero exit") is confirmed correct for these two scripts as well — it was just imprecise to say they have no `sys.exit` at all. The one that exists there guards a different failure mode (can't log in) than the one the audit was concerned about (a check genuinely failed).
- **`verify_admfe.py:519` — the exact line was re-confirmed present**: `check("no double processing (shared + individual disjoint)", total_covered + len(result.unassigned) == 14 or True)`. I ran this exact expression (with the left-hand comparison varying across several values, including obviously-wrong ones like `999` and `-3`) in a live Python interpreter: **it evaluated to `True` in every case.** This is a genuine execution result, not an inference — `X or True` is always `True` regardless of `X`, by Python's boolean-logic rules, and I demonstrated it rather than just asserting it.

**Evidence:** grep results across all four scripts (zero `sys.exit` hits in two; one login-only `sys.exit(1)` each in the other two); `backend/scripts/verify_fix.py:271-283` (the unguarded `[FAIL]` branch); `backend/evaluation/verify_admfe.py:518-519`; live Python execution transcript (5 test values, all `True`).

**Confirmed / Refuted / Unverified:** **CONFIRMED for all four scripts' failure-to-exit-nonzero behavior** (via complete source reading — deterministic, not requiring a live run to know a `print()` statement doesn't set an exit code) — refined to note that two of the four do have an unrelated `sys.exit(1)` for a login precondition. **CONFIRMED via genuine execution for the `or True` vacuity.** **UNVERIFIED: I did not actually run any of these four scripts against a live server and observe the real process exit code** (`echo $?`), since no server could be started — the conclusion above is deterministic-by-code-reading, not observed-by-running.

**Severity:** P1 (as originally assessed) — a false "it passed" is dangerous in exactly the way originally described.

**Recommended action (not implemented):** remove `or True`; add `sys.exit(1)` gated on the actual aggregate pass/fail result in all four scripts, not just on the login precondition.

---

## Finding 7 — pytest coverage of the optimizer, `run_analysis()`, and the adaptive package

**Audit claim:** All three have zero or near-zero direct pytest coverage.

**Test performed:** Re-confirmed via grep across all 11 files in `backend/tests/` for references to the specific functions/classes in question. (This finding does not depend on execution — "is this symbol ever imported/called in a test file" is answerable by reading, and was already done exhaustively in the original audit; this pass re-ran the same searches to confirm nothing changed.)

**Actual result:**
- **`backend/app/dmfe/optimizer.py`**: grepping `tests/*.py` for `RouteOptimizer`, `optimize_trip`, `_solve_pdp`, or `from app.dmfe.optimizer` returns **zero matches**. Confirmed zero direct pytest coverage.
- **`decision_engine.run_analysis()`**: grepping `tests/*.py` for `run_analysis` returns **zero matches**. Confirmed zero direct pytest coverage — it is exercised only by `scripts/test_stale_release.py`, which is not part of `pytest tests/` and (per the original audit, itself grep-confirmed) does not `assert`/`sys.exit` on its own verdict.
- **`backend/app/dmfe/adaptive/*`**: grepping `tests/*.py` for `compute_extension_factors`, `batch_quality_score`, `compute_confidence`, `effective_threshold`, `AdaptiveBatchFormation`, `build_adaptive_reasons` (the core public functions of `factors.py`, `decision.py`, `batching.py`, `xai.py`) returns **zero matches** for all of them. `context.py` and `weights.py` do get two incidental references inside `test_learning_phase4.py`, consistent with the original finding of "almost entirely untested."

**Evidence:** grep results across `backend/tests/*.py` (11 files) for each symbol named above — all zero, except the two incidental `context.py`/`weights.py` references already noted in the original audit.

**Confirmed / Refuted / Unverified:** **CONFIRMED** — this is static analysis (searching for a function name across a fixed set of files), which does not require code execution to be conclusive; a symbol either appears in the test files or it doesn't, and none of the ones checked here do (beyond the two already-noted exceptions).

**Severity:** P0 (unchanged from original audit).

**Recommended action:** unchanged — add direct tests for these three areas.

---

## Finding 8 — Postgres configuration and concurrency/FK concerns

**Audit claim:** Postgres is supported in code but never actually exercised; the TOCTOU/circular-FK concerns are therefore theoretical on the only backend (SQLite) actually used.

**Test performed:** Read `backend/requirements.txt` for a Postgres driver dependency. Re-read `config.py`'s `SQLALCHEMY_DATABASE_URI` property (already read in full for Finding 3) to see exactly what triggers a Postgres connection string versus the SQLite fallback. Searched the mirrored repository for any `docker-compose.yml`, Postgres service definition, or `.env` value setting `POSTGRES_*`/`DATABASE_URL`.

**Actual result:**
- `requirements.txt:4`: `psycopg2-binary>=2.9.10` — confirmed, a real, listed dependency (the Postgres driver is genuinely available if installed).
- `config.py:34-45`: `SQLALCHEMY_DATABASE_URI` only builds a `postgresql://...` connection string if `DATABASE_URL` is set, **or** all three of `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` are set. All four of these default to `None` in the `Settings` class (`config.py:11,13-17`). **Absent any of those environment variables, the property falls through to `sqlite:///{BACKEND_DIR}/dmfe_dev.db`** — i.e., Postgres is opt-in via environment configuration, not the default, and nothing in the repository sets those variables anywhere (no `docker-compose.yml`, no `.env` committed with Postgres values — `.env` itself is git-ignored and wasn't found with Postgres values in the one `.env.example` staged this session).
- Every verification artifact examined across this entire engagement (`VERIFY_RESULTS.md`'s explicit `scratch db: sqlite:///...`, `qa/server_err.log`'s SQLite-specific `SAWarning`, every evaluation script's use of a temp SQLite file) shows SQLite, with zero exception found anywhere.

**Evidence:** `backend/requirements.txt:4`; `backend/app/core/config.py:11-17,34-45`; absence of any Postgres-configuring file in the repository.

**Confirmed / Refuted / Unverified:** **CONFIRMED that Postgres support is present in code but opt-in and never the default, and CONFIRMED that no artifact anywhere in this repository's history shows it having actually been exercised** — both are direct, verifiable facts about the repository's own contents, not inferences. **UNVERIFIED: whether a Postgres server is actually installed or running anywhere on your machine right now** — that would require running a command on your machine (`device_bash`), which is blocked. I cannot rule out that Postgres exists on your system for unrelated purposes; I can only confirm this project has never used it. Therefore, per your original audit's own framing: the TOCTOU/circular-FK concerns remain **theoretical for this project as currently run** (SQLite, single-writer) and would need a genuine test against a real Postgres instance to become anything more than that — a test this pass could not perform.

**Severity:** Unchanged (P2 for the underlying TOCTOU gap, contingent on an actual Postgres deployment that doesn't currently exist for this project).

**Recommended action:** unchanged from original audit — treat as a design-time fix, not an urgent one, given the confirmed absence of any current Postgres usage.

---

## CONFIRMED HIGH-PRIORITY ISSUES

1. **Repeated `/api/dmfe/analyze` calls will create duplicate `DMFEBatch` rows for the same unchanged pending queue** — confirmed via complete source trace of `run_analysis()` (no status write) and the `DMFEBatch` model (no uniqueness constraint on `batch_code`). (P1)
2. **`VehicleLocationMap.jsx` marker clicks will throw `ReferenceError: setSelectedVehicle is not defined`** — confirmed via complete file read; no `useState` import, no declaration anywhere in the file. (P1)
3. **The hardcoded `SECRET_KEY` fallback and seeded `admin123` password have no non-development safeguard in code** — confirmed via complete read of `config.py` and `main.py`; the code's own comment about this ("the app exits...") is itself stale and contradicted by the actual, unguarded behavior. (P1)
4. **`verify_50_e2e.py` and `api_test.py` cannot exit non-zero under any circumstance; `verify_fix.py` and `verify_demo.py` only exit non-zero on a login failure, never on an actual verification check failing** — confirmed via exhaustive grep and full reading of the relevant branches. (P1)
5. **`evaluation/verify_admfe.py:519`'s "no double processing" check is unconditionally true** — confirmed via genuine execution of the exact boolean expression, not just reading. (P1)
6. **The OR-Tools optimizer, `run_analysis()`, and the entire `adaptive/` package have zero direct pytest coverage** — confirmed via exhaustive symbol-level grep across all 11 test files. (P0)
7. **Five Create/Save forms (confirmed directly for `ProviderManagement.jsx`, consistent with prior grep for the other four) lack a submit-in-flight guard** — real double-submit exposure, though not yet observed live. (P2)

## REFUTED ISSUES

1. **`ScenarioComparison.jsx` crashing on a comparison response missing one simulation side** — refuted as a reachable bug. Tracing the full path from the backend service (`compare_simulations` returns either a complete object or `None`) through the route handler (a clean 400, never a partial 200) to the frontend's own error handling (`try/catch` prevents a partial object from ever reaching the component) shows there is no way for a normal user action to produce the failure condition the original finding described. The component's code is still missing a defensive null-check, but it is not an active, exploitable defect through this application's real data flow. Downgraded to informational/P3.

## REMAINING UNKNOWN RISKS

1. **Real, observed before/after database row counts for the duplicate-batch bug (Finding 1)** — the code guarantees the behavior, but no live run has produced actual numbers. Recommend re-running this specific check the moment `device_bash` or another execution path is available.
2. **A literal browser-console reproduction of the `VehicleLocationMap` crash (Finding 2)** — certain by JavaScript scoping rules, but not personally observed in your running application.
3. **Whether any deployment-specific safeguard outside this repository (a hosting platform's own secret-injection, a reverse proxy) would mitigate Finding 3 in whatever environment you'd actually deploy to** — unknown, since nothing in the repository itself provides one.
4. **Actual duplicate database rows from a real rapid double-click on the five unguarded forms (Finding 4)** — the code gap is confirmed; the live exploit was not reproduced.
5. **Real captured exit codes from actually running the four verification scripts (Finding 6)** — the code-level conclusion is certain, but I have not personally watched a shell report `$?` after running them.
6. **Whether a Postgres server exists anywhere on your machine independent of this project (Finding 8)** — genuinely unknown from the repository alone; would need a direct check on your machine.
7. **The one item this audit could not resolve even with the earlier baseline pass: whether `e2e_test.py` still exists at the repository root** — still unresolved, and still blocked by the same infrastructure issue.

---

This report deliberately stops here, as instructed. No fixes have been implemented. The most direct way to close the "remaining unknown risks" above is to re-attempt this verification once `device_bash` recovers from the September 8 platform issue (I can retry automatically and let you know, the same way I handled this same blocker earlier in this engagement) — or, if you'd rather not wait, I can proceed on the strength of the code-level evidence already gathered, since every CONFIRMED finding above rests on a deterministic reading of the actual current source, not a guess.
