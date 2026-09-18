# Evaluation and Experiments

## Evaluated Claims (R1.1, R1.3, R1.4, R1.5, R2.1)
The `evaluation/framework.py` executes isolated, deterministic evaluations.

### Methodology
- Database reset per workload.
- Haversine deterministic routing (Google Maps disabled).
- Simulation model executes trips, adding simulated noise (scatter/bias) to actuals.
- Learning engine updates based on actuals vs predictions.

### Metrics Collected
- Batching Rate, Shared Trips, Total Distance, Fuel Saved, CO2 Saved, Completion Rate.

### Limitations (CRITICAL)
- **R1.3**: Solves the pairing sub-problem only (triple expansion is heuristic).
- **R1.5**: This is a pure mathematical simulation, not a human driver study.
- **R1.1**: Synthetic robustness sweep (noise injection), not real-world traffic data.
- **R2.1**: Actual max_allowed_delay_min configuration sweep.

*Never strengthen these claims beyond the implemented simulation evidence.*
