# Frontend Map

## Architecture
- React/Next.js/Vite based Single Page Application.
- State management likely Context or Redux.

## Key Views
- **Dashboard**: High-level metrics, system status, active trips.
- **Request Simulator**: Panel to generate simulated traffic (ride, food, parcel).
- **DMFE Monitor**: Visualizes the decision engine, batches, candidate groups, and rejection reasons.
- **Configuration Panel**: Controls weights, threshold, A-DMFE mode toggles.

## Performance Bottlenecks
- Excessive polling on active trips.
- Full table loads for batch histories.
