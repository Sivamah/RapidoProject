# API Map

## Endpoints

### DMFE / Config
- **GET /api/config** - Retrieves dynamic thresholds and weights.
- **PUT /api/config** - Updates settings (triggers adaptive changes).
- **GET /api/dmfe/runs** - Lists DMFE analysis runs.
- **GET /api/dmfe/batches** - Lists batches and decision reasons.

### Requests / Dispatch
- **POST /api/requests/simulate** - Generates simulation traffic.
- **GET /api/requests/pending** - Fetches the pending queue.
- **POST /api/engine/run** - Triggers a manual pipeline dispatch.

## Known Issues
- Large query limits may cause heavy DB load if polling is high.
- Polling `dmfe/batches` in UI might lack cursor-based pagination.
