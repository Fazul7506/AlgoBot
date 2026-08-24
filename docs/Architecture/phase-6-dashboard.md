# Phase 6 — Dashboard

Status: COMPLETE AND WORKING

## Scope

The dashboard is now the first complete downstream page consuming the shared broker state/data architecture.

## Implemented

- removed inline dashboard data-fetching JavaScript
- added `static/js/dashboard.js`
- dashboard account KPIs consume `window.AlgoBotBrokerState`
- positions, orders and market data use the centralized frontend data contract
- dashboard refuses to load broker-backed datasets while no broker is connected
- disconnected/no-broker states are explicit and never replaced with fake values
- signals are requested only for a symbol selected from backend market data rather than the old implicit dashboard default
- kill switch action is routed through the centralized backend request contract and only reports success after backend confirmation
- dashboard uses the shared design system and existing responsive dashboard CSS
- initial HTML contains `Unavailable`/waiting states rather than invented trading values

## Data flow

`Broker -> broker service -> API/WebSocket -> AlgoBotBrokerState -> dashboard.js -> DOM`

For dashboard actions:

`User -> dashboard.js -> AlgoBotFrontendData -> Django -> broker/backend command -> confirmed response -> UI`

## Test coverage

`core/tests/test_dashboard_template_contract.py` verifies the authenticated dashboard renders without embedded example trading/account values and starts from an unavailable broker-backed state.

## Important deliberate behavior

Net P/L remains `Unavailable` until the backend exposes a broker-confirmed P/L field on the canonical account contract. The dashboard does not derive or invent P/L from unrelated local data.

## Verification note

No GitHub Actions workflow run is exposed for the current commit. Targeted repository test coverage has been added; browser/backend/broker end-to-end validation remains part of Phase 19.
