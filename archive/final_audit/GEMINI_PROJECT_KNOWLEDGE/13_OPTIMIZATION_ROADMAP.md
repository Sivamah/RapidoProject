# Optimization Roadmap

## Priorities
- **P0 — Critical correctness**: None found blocking execution.
- **P1 — Performance**: Implement caching for haversine distances in `CompatibilityCalculator` (Effort: Low, Risk: Low). Bulk load driver pools in `DriverSelector` (Effort: Low, Risk: Low).
- **P2 — Architecture**: Move DMFE execution to a Celery worker to prevent API blocking (Effort: Medium, Risk: Medium).
- **P3 — Maintainability**: Clean up Phase 8 legacy config keys and `avg_waiting_min` aliases.
- **P4 — UI/UX**: Switch frontend from polling to WebSockets for live trips.

*Note: Changes to core algorithms (P5) must not break reproducibility of IEEE evaluation scripts.*
