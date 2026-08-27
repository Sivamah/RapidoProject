# PROJECT FILE & CODE AUDIT

## 1. Repository Statistics
* **Total Files**: 275 (excluding standard ignore directories)
* **Total Folders**: 42
* **Python Files**: 84
* **JS/JSX Files**: 52
* **Markdown Files**: 38

## 2. Core Files
Core components ensuring A-DMFE research reproducibility, deployment, and evaluation are confirmed intact. No active tests, active frontend components, API routes, or database models were moved.

## 3. Unused Files
Based on static analysis (`knip` and manual grep verification), the following frontend components and pages are not imported or registered:
| File | Category | Evidence | Risk | Action |
|------|----------|----------|------|--------|
| `frontend/src/components/dashboard/AIEngineStatus.jsx` | UNUSED | Not imported | Low | Report Only |
| `frontend/src/components/dashboard/DashboardCharts.jsx` | UNUSED | Not imported | Low | Report Only |
| `frontend/src/components/dashboard/DashboardKpis.jsx` | UNUSED | Not imported | Low | Report Only |
| `frontend/src/components/dashboard/DashboardSummary.jsx` | UNUSED | Not imported | Low | Report Only |
| `frontend/src/components/map/MapFilters.jsx` | UNUSED | Hardcoded inline in Dashboard.jsx | Low | Report Only |
| `frontend/src/components/ui/Modal.jsx` | UNUSED | Local hardcoded implementations in use | Low | Report Only |
| `frontend/src/pages/DashboardOverview.jsx` | UNUSED | Not imported in App.jsx routing | Low | Report Only |

## 4. Unused Code
| File | Category | Evidence | Risk | Action |
|------|----------|----------|------|--------|
| `frontend/src/components/map/RequestMarkers.jsx` | UNUSED | Export `createGoogleMarkerSvg` is unused | Low | Report Only |
| `frontend/src/services/api.js` | UNUSED | Export `invalidateCache` is unused | Low | Report Only |
| `frontend/src/utils/coimbatore.js` | UNUSED | Exports `COIMBATORE_BOUNDS`, `isInCoimbatore`, `validateCoimbatore` unused | Low | Report Only |

*(Note: Vulture identified some variables in `backend/app/db/database.py` and `evaluation/framework.py`, but manual reference analysis verified they are required keyword arguments for SQLAlchemy event hooks, thus they are false positives.)*

## 5. Duplicate Files
* `backend/.fuse_hidden0000003300000001` vs `backend/.fuse_hidden0000003600000003` (Temporary NFS/Fuse hidden files)
* `backend/.fuse_hidden0000003500000002` vs `backend/.fuse_hidden0000003700000004` (Temporary NFS/Fuse hidden files)

## 6. Files Archived
The following clearly historical QA, Audit, and Bugfix reports were moved into `archive/project_audit/`:
* `archive/project_audit/reports/AUDIT_REPORT_v3.md`
* `archive/project_audit/reports/DMFE_ORCHESTRATION_FIX_PLAN.md`
* `archive/project_audit/reports/FIX_REPORT_v2.md`
* `archive/project_audit/reports/VERIFY_RESULTS.md`
* `archive/project_audit/qa/CLAUDE_HANDOFF.md`
* `archive/project_audit/qa/FINAL_PASS_REPORT.md`
* `archive/project_audit/qa/FINAL_RESEARCH_VALIDATION.md`
* `archive/project_audit/qa/manual_test_report.md`

## 7. Files Intentionally Not Archived (MANUAL REVIEW REQUIRED)
These documents appear to be current research validation or active working docs, and were intentionally left in their original locations per user request.
* `docs/01_Project_Validation_Report.md` through `docs/13_Final_Freeze_Report.md`
* `docs/A-DMFE_MANUAL_LIVE_QA_REPORT.md`

## 8. Final Recommended Project Structure
```text
rapidoproject/
├── archive/
│   └── project_audit/
│       ├── duplicates/
│       ├── generated/
│       ├── old_scripts/
│       ├── qa/
│       ├── reports/
│       └── screenshots/
├── backend/
│   ├── app/
│   ├── datasets/
│   ├── evaluation/
│   ├── migrations/
│   ├── scripts/
│   └── tests/
├── docs/
│   └── PROJECT_FILE_CODE_AUDIT.md
├── frontend/
│   ├── public/
│   └── src/
└── paper/
```

## 9. Recommended .gitignore entries
```gitignore
# Temporary file system mounts
.fuse_hidden*
# Local analysis output
repo_stats.json
```
