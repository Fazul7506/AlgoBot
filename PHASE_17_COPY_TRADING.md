# Phase 17 — Copy Trading

Implemented a cumulative Copy Trading Control Center.

Frontend:
- `/copy-trading/`
- provider discovery
- provider performance/risk metrics
- subscribe/activate provider
- pause/resume/stop copying
- follower allocation
- copy multiplier
- max daily loss
- max drawdown
- max trade stake
- max concurrent trades
- loss-streak pause
- dry-run copied signal
- copied-trade history

Backend API:
- GET `/api/copy-trading/dashboard/`
- POST `/api/copy-trading/subscribe/`
- POST `/api/copy-trading/pause/`
- POST `/api/copy-trading/resume/`
- POST `/api/copy-trading/stop/`
- POST `/api/copy-trading/risk/`
- POST `/api/copy-trading/test/`

Execution principle:
Provider signals are never sufficient authorization by themselves. The follower's limits and the platform risk engine remain authoritative.
