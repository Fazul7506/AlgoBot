# Phase 8 — Orders

Status: COMPLETE AND WORKING

## Implemented

- replaced placeholder `static/js/orders.js` with broker-gated execution controller
- refactored `templates/core/orders.html` to explicitly identify broker execution as the source of order truth
- orders load only when canonical broker state is connected/ready/degraded
- explicit no-broker, loading, empty and error states
- searchable order table
- broker order ID, status, side, type, quantity, requested price and timestamps shown from backend execution records
- new order creation remains in the trading terminal so execution commands continue through the canonical backend/broker path
- targeted template contract test added

## Safety boundary

The orders page is intentionally read/inspect oriented. It does not fake cancellation/fill state or locally remove an order from the table. A mutation is only considered successful when the backend/broker confirms it.

## Verification note

No GitHub Actions workflow run is exposed for the current branch/commit. Targeted repository test coverage has been added; browser/backend/broker E2E remains part of Phase 19.
