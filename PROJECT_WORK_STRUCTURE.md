# PROJECT WORK STRUCTURE

## Purpose

This document defines where **NEW** files go during active development.

**Preservation-first rule:** existing files stay exactly where they are. Nothing
in this guide should be read as permission to move, rename, or delete existing
files or folders. A complete cleanup, deduplication, dead-code removal, and
final restructuring will happen **only after** the project is fully finished.

The canonical layout to follow for new work:

```
project/
├── backend/
│   ├── app/          # production source code (FastAPI + DMFE/A-DMFE engine)
│   ├── tests/        # pytest test suite
│   ├── evaluation/   # application-specific experiments + benchmarks
│   ├── scripts/      # dev/QA/support scripts
│   ├── datasets/     # source datasets (existing, unchanged)
│   └── data/         # NEW: runtime data artifacts / DB dumps
├── frontend/
│   ├── src/          # React source (components, pages)
│   └── public/       # static assets
├── docs/
│   ├── research/     # NEW: research notes / contributions
│   ├── reports/      # NEW: final & evaluation reports
│   ├── debugging/    # NEW: debug session notes (never in source dirs)
│   └── architecture/ # NEW: design / architecture docs
├── experiments/      # NEW: exploratory, standalone (non-app) experiments
├── temp/             # NEW: temporary / debug scratch (gitignored)
└── archive/          # existing archive location (singular) — reused
```

## Where new files go

| Kind | Location |
|------|----------|
| **Backend source / feature code** | `backend/app/` — add to the relevant existing module (e.g. `dmfe/`, `api/routes/`, `services/`). Do not reorganize DMFE/A-DMFE structure. |
| **Frontend source** | `frontend/src/` (components, pages), `frontend/public/` (static assets). |
| **Tests** | `backend/tests/` as `test_*.py`, following existing test conventions. |
| **Experiments — application-specific** | `backend/evaluation/` (scripts), scratch DBs under `backend/evaluation/experiments/`, results under `backend/evaluation/results/`. |
| **Experiments — standalone / exploratory (not app-tied)** | `experiments/`. |
| **Benchmark scripts + results** | `backend/evaluation/` (scripts) and `backend/evaluation/results/` (output JSON/CSV). Application benchmarks belong here. |
| **Reports** | `docs/reports/`. |
| **Research / contribution notes** | `docs/research/`. |
| **Architecture / design docs** | `docs/architecture/`. |
| **Debug session / scratch notes** | `docs/debugging/`. Never place debug scratch in production source dirs. |
| **Temporary / throwaway scripts & artifacts** | `temp/` (gitignored). |
| **Runtime data artifacts, DB dumps** | `backend/data/`. (Source datasets stay in `backend/datasets/`.) |

## Things that must NOT be touched during development

- **DMFE / A-DMFE engine structure** — `backend/app/dmfe/**` and `backend/app/dmfe/adaptive/**`. Do not restructure for cleanup.
- **Working imports / application behavior** — never change an import or a config that would alter runtime behaviour just for organisation.
- **Existing folders and files** — `archive/`, all current `docs/*.md` and `*.docx`/`*.pdf`, `paper/`, `qa/`, `GEMINI_PROJECT_KNOWLEDGE/`, `backend/datasets/`, loose root scripts and DB files. All preserved as-is until the final cleanup.
- **Source datasets** — added to `backend/datasets/`, never `backend/data/`.

## Notes on existing convention

- `backend/evaluation/results/` already holds evaluation/benchmark outputs (e.g.
  `scalability_benchmark_100_150_250.json`) and `backend/evaluation/experiments/`
  holds the eval scratch DBs. New application benchmark work continues there.
- `archive/` (singular) is the established archive location and is reused; there
  is no plural `archives/`.
- `temp/` is the designated scratch area and is excluded from version control.

## When to clean up

Do **not** perform cleanup now. Revisit this file only after the project is
fully finished, then execute the complete cleanup, deduplication, dead-code
removal, and final folder restructuring as a dedicated, separate effort.
