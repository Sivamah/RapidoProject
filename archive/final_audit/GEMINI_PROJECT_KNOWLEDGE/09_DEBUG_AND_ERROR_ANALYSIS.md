# Debug and Error Analysis

## Identified Issues
1. **Unreachable Code / Warnings**:
   - `broad exception` blocks seen in `analyze_backend.py` output (e.g., in exception handling for batch generation errors).
2. **Missing Null Handling**:
   - Some fields like `demand` or `weight_kg` might default to None in DB, requiring defensive `(r.demand or 1)` checks throughout `decision_engine.py`.
3. **Hardcoded Limits**:
   - Maximum batch size constrained to 3 (triple expansion) in `adaptive/batching.py`.
4. **Technical Debt**:
   - Legacy Phase 8 config keys are preserved for backward compatibility but clutter the config space.
   - `avg_waiting_min` is an alias for `avg_delay_min` in reports; actual passenger wait time is not recorded.

**Classification Summary**:
- Confirmed Bugs: 0
- High-Risk Bugs: 0
- Technical Debt: 3 instances
