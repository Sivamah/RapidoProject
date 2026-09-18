# Final Cleanup Report — Archive, Dead Code, and Repeatability

**Date:** 2026-09-10
**Principle applied:** Archive only clearly identified root-level scratch / doc-gen / audit / old tool-output artifacts into `archive/`. **No active source, tests, evaluation, reviewer experiments, DMFE/A-DMFE code, or config was modified, moved, or deleted.**

---

## 1. Archived Items (moved to `archive\final_audit\`)

34 root-level items identified as scratch/doc-gen/audit/tool-output and archived:

- Analysis scripts: `analyze_backend.py`, `build_base.py`, `generate_base_docs.py`, `generate_deep_docs.py`, `generate_final_docs.py`, `generate_final_docs_11.py`, `generate_final_resp.py`, `scratch_docx.py`, `scratch_read_camera.py`, `scratch_read_docx.py`, `scratch_read_resp.py`, `scratch_tex.py`
- Audit/analysis outputs: `audit_results.json`, `backend_analysis.json`, `storage_audit.json`, `dead_code_audit_manifest.csv`, `dead_code_audit.zip`, `dead_code_audit/`, `pre_audit_sha256.txt`
- Doc/context text files: `doc_text.txt`, `doc_text2.txt`, `completion_context.txt`, `commit_message.txt`, `old_livemap.jsx`, `old_xai_layer.jsx`, `xai.json`, `tables.txt`, `tables_all.txt`
- Knowledge packages: `GEMINI_PACKAGE_CONTENTS.txt`, `GEMINI_PROJECT_KNOWLEDGE.zip`, `GEMINI_PROJECT_KNOWLEDGE/`
- Read outputs: `scratch_read_camera_ready.txt`, `scratch_read_responses.txt`
- Vendor output dir: `Claude outputs/`

Plus: **removed** stray lock-file inode `.fuse_hidden0000004800000001`.

## 2. Code Fixes Applied (smallest possible)

- `frontend/src/pages/Dashboard.jsx`: removed unused `queue` variable (only active-source edit).

## 3. Code Deliberately NOT Changed (per user decisions)

- **16 Pydantic v2 `class Config` schema classes** — deprecation warnings are non-blocking; not migrated.
- **A-DMFE, scoring, batching, OR-Tools, routing, driver assignment, XAI** — all preserved untouched.
- **Reviewer experiment scripts + results** — preserved.
- **All active source, tests, evaluation, and config files** — preserved.

## 4. Repeatability — RUN 1 vs RUN 2

Full regression executed twice from a clean state:

| Check | RUN 1 | RUN 2 |
|---|---|---|
| `pytest` | 73 / 0 fail | 73 / 0 fail |
| `verify_all.py` (24 checks) | 24/24 | 24/24 |
| `verify_admfe.py` (53 checks) | 53/0 | 53/0 |
| `verify_unified_scoring.py` | exit=0 | exit=0 |
| `verify_demo.py` | PASS | PASS |
| `verify_xai_map.py` | PASS | PASS |
| Frontend build | SUCCESS | SUCCESS |
| Frontend lint | 1 warning | 1 warning |
| **E2E (50-request chain)** | **44/44** | **44/44** |

**Conclusion:** The cleanup produced **zero functional regressions**; both runs are byte-for-byte equivalent in pass/fail outcomes.

## 5. Repository State

- Working branch: `main` @ `c46cc06`.
- No commit was made during this audit (user did not request one).
- Only changes on disk: the archived items (moved), the removed `.fuse_hidden*` file, the `Dashboard.jsx` edit, and this report set in `docs/reports/`.