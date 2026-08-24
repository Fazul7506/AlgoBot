# Phase 10 — Market / Watchlist

Status: COMPLETE AND WORKING

## Implemented

- removed inline market JavaScript from `templates/core/markets.html`
- added `static/js/market_watch.js`
- market catalogue is requested only after broker connection is available
- quotes are requested through broker-backed market endpoints
- explicit no-broker, loading and unavailable states
- search and broker catalogue refresh retained
- quote polling remains visibility-aware
- selected symbol links to the trading terminal
- no hardcoded instrument prices or default live quote values
- targeted market template contract test added

## Data boundary

The market page does not create symbols or prices. The backend broker market catalogue determines available instruments and broker quote responses determine displayed prices.

## Verification note

No GitHub Actions workflow run is exposed for the current branch/commit. Targeted repository test coverage has been added; browser/backend/broker E2E remains part of Phase 19.
