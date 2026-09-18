# Dead Code Audit Report

**Project:** AI-Powered Unified Mobility and Delivery System (A-DMFE)
**Date:** 2026-09-02
**Scope:** Complete repository-wide dead code analysis
**Constraint:** Audit-only - no source files modified

---

## Executive Summary

| Category | Count |
|----------|-------|
| Definitely Dead Files | 17 |
| Probably Dead Files | 12 |
| Duplicate/Legacy Files | 5 |
| Dead Artifacts | 11 |
| Dead Dependencies | 5 |
| Code-level Dead Code Locations | 5 |
| Uncertain (Manual Review) | 4 |
| Active Files (DO NOT TOUCH) | 250+ |
| **Total Files Scanned** | **340** |

---

## A. DEFINITELY DEAD (No runtime/reference path found)

### Frontend (6 files)

| # | File | Reason | Evidence |
|---|------|--------|----------|
| 1 | frontend/src/pages/DashboardOverview.jsx | Not routed in App.jsx, not imported by any file | Zero import hits across entire codebase |
| 2 | frontend/src/components/map/MapFilters.jsx | Never imported by any component or page | Zero import hits |
| 3 | frontend/src/components/dashboard/DashboardKpis.jsx | Only imported by #1 (dead page) | DashboardOverview.jsx:9 |
| 4 | frontend/src/components/dashboard/AIEngineStatus.jsx | Only imported by #1 (dead page) | DashboardOverview.jsx:10 |
| 5 | frontend/src/components/dashboard/DashboardSummary.jsx | Only imported by #1 (dead page) | DashboardOverview.jsx:11 |
| 6 | frontend/src/components/dashboard/DashboardCharts.jsx | Only imported by #1 (dead page) | DashboardOverview.jsx:14 |

The entire frontend/src/components/dashboard/ subdirectory is transitively dead.

### Backend (2 files)

| # | File | Reason | Evidence |
|---|------|--------|----------|
| 7 | backend/app/engine/optimizer.py | AIOrchestrator - sole route returns 410 | orchestration.py:84-117 raises 410; docstring says no caller |
| 8 | backend/app/engine/explainability.py | Zero imports anywhere in entire codebase | grep found 0 import references |

### Root Scripts (8 files, all untracked in git)

| # | File | Reason | Evidence |
|---|------|--------|----------|
| 9 | scratch_analysis_r1.py | Unreferenced scratch script | Zero imports, untracked |
| 10 | scratch_baseline_r1.py | Unreferenced scratch script | Zero imports, untracked |
| 11 | scratch_r1_3.py | Unreferenced scratch script | Zero imports, untracked |
| 12 | scratch_r1_4.py | Unreferenced scratch script | Zero imports, untracked |
| 13 | scratch_r1_5.py | Unreferenced scratch script | Zero imports, untracked |
| 14 | scratch_per_service_r1.py | Unreferenced scratch script | Zero imports, untracked |
| 15 | scratch_repro.py | Unreferenced scratch script | Zero imports, untracked |
| 16 | payload.json | API test payload, zero references | Zero hits anywhere |

---

## B. PROBABLY DEAD (No runtime path, but standalone scripts may be manually invoked)

### Root Document Scripts (7 files, all untracked)

| # | File | Reason | Evidence |
|---|------|--------|----------|
| 17 | generate_final_docs.py | DOCX generator standalone untracked | Zero imports |
| 18 | generate_final_docs_11.py | Variant DOCX generator untracked | Zero imports |
| 19 | generate_final_resp.py | Response DOCX generator untracked | Zero imports |
| 20 | scratch_docx.py | DOCX reader utility untracked | Zero imports |
| 21 | scratch_tex.py | LaTeX generator untracked | Zero imports |
| 22 | scratch_read_resp.py | Response text extractor untracked | Zero imports |
| 23 | scratch_read_camera.py | Camera-ready text extractor untracked | Zero imports |

### Root Text Output Files (5 files)

| # | File | Reason | Evidence |
|---|------|--------|----------|
| 24 | doc_text.txt | Scratch output zero references | Zero hits anywhere |
| 25 | doc_text2.txt | Scratch output zero references | Zero hits anywhere |
| 26 | tables.txt | Scratch output zero references | Zero hits anywhere |
| 27 | tables_all.txt | Scratch output zero references | Zero hits anywhere |
| 28 | completion_context.txt | Scratch output zero references | Zero hits anywhere |

---

## C. DUPLICATE / LEGACY (5 files)

| # | File | Reason | Evidence |
|---|------|--------|----------|
| 29 | scratch_read_docx.txt | Output of dead script scratch_docx.py | Written by scratch_docx.py |
| 30 | scratch_read_camera_ready.txt | Output of dead script scratch_read_camera.py | Written by scratch_read_camera.py |
| 31 | scratch_read_responses.txt | Output of dead script scratch_read_resp.py | Written by scratch_read_resp.py |
| 32 | commit_message.txt | Only in .gitignore + archived docs | No code references |
| 33 | storage_audit.json | Only referenced in docs prose | docs/STORAGE_OPTIMIZATION_REPORT.md |

---

## D. DEAD ARTIFACTS (11 files)

| # | File | Reason | Evidence |
|---|------|--------|----------|
| 34 | dmfe_dev.db (root copy) | Orphan DB copy | config.py uses BACKEND_DIR/dmfe_dev.db |
| 35 | .fuse_hidden0000004800000001 | NFS/FUSE temp artifact | .gitignore + docs describe as safe to delete |
| 36-39 | backend/.fuse_hidden* (4 files) | NFS/FUSE temp artifacts | Same as above |
| 40 | backend/server_out.log | Unreferenced server log | No code references |
| 41 | backend/server_err.log | Unreferenced server log | No code references |
| 42 | backend/qa_test.db-shm | SQLite temp file | No direct references |
| 43-44 | eval.db-wal, eval.db-shm | SQLite temp files | Standard SQLite artifacts |

---

## E. DEAD DEPENDENCIES

### Python
- **slowapi** - UNUSED - Zero imports anywhere in backend

### JavaScript
- **autoprefixer** - UNUSED - No source usage; Tailwind v4 handles internally
- **postcss** - UNUSED - No source usage; Tailwind v4 Vite plugin handles it
- **@testing-library/jest-dom** - MISSING - Referenced in setupTests.js but not installed
- **vitest** - MISSING - Configured in vite.config.js but not installed

---

## F. CODE-LEVEL DEAD CODE (within active files)

| # | File:Line | What | Reason |
|---|-----------|------|--------|
| 1 | backend/app/dmfe/scoring.py | 5 factor wrapper functions | compatibility.py re-implements math inline |
| 2 | backend/app/api/routes/orchestration.py:84-117 | run_optimization route | Tombstone raises 410 |
| 3 | frontend/src/utils/coimbatore.js | 3 unused exports | Only COIMBATORE_CENTER is imported |
| 4 | frontend/src/setupTests.js | Entire file | Imports non-installed package no test files exist |
| 5 | backend/app/dmfe/scoring.py | DEFAULT_WEIGHTS duplicate | compatibility.py has its own weight constants |

---

## G. UNCERTAIN - MANUAL REVIEW

| # | File | Reason | Confidence |
|---|------|--------|------------|
| 52 | backend/seed_users.py | Standalone seeding script may be manually invoked | 60% dead |
| 53 | backend/scripts/run_dev.sh | Standalone launcher only self-referenced | 70% dead |
| 54 | backend/scripts/run_qa.sh | Standalone launcher only self-referenced | 70% dead |

---

## H. ACTIVE FILES - DO NOT TOUCH

### Backend Core (all active)
- backend/app/main.py - FastAPI entry point 12 router registrations
- backend/app/core/ - config.py security.py middleware.py json_utils.py coimbatore.py
- backend/app/db/ - database.py models.py
- All backend/app/api/routes/*.py (12 files)
- All backend/app/schemas/*.py (10 files)
- All backend/app/services/*.py (7 files)
- backend/app/engine/distance.py - Critical utility (10+ importers)

### DMFE Engine (all active)
- backend/app/dmfe/ - All 10 core modules
- backend/app/dmfe/adaptive/ - All 9 adaptive modules

### Frontend (all active)
- frontend/src/main.jsx App.jsx index.css
- All 15 pages (all routed)
- All component subdirectories (analytics config dmfe drivers map notifications playback ui xai)
- frontend/src/context/AuthContext.jsx
- frontend/src/services/api.js
- frontend/src/utils/coimbatore.js

### Tests (all active)
- All 9 backend test files
- All verification scripts

### Evaluation (all active - standalone research tools)
- All 9 evaluation scripts
- All evaluation results

---

*Report generated by dead code audit - 2026-09-02*
