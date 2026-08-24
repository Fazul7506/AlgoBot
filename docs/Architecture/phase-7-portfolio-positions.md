# Phase 7 — Portfolio / Positions

Status: COMPLETE AND WORKING

## Positions

`templates/core/positions.html` and `static/js/positions.js` now provide a broker-gated live position view.

- no broker connection -> no position data request
- connected broker -> `/api/positions/open/`
- explicit synchronization/loading/error/empty states
- searchable position table
- broker-backed symbol, side, size, entry, current price, P/L and status
- no fabricated rows or fallback account values

## Portfolio

`templates/portfolio/dashboard.html` and `static/js/portfolio_dashboard.js` now provide a broker-backed portfolio surface.

Portfolio KPIs are derived only from:

- canonical broker account balance/equity
- broker-backed open positions
- broker-reported position profit
- position size/current price for derived gross exposure

Allocation is derived from the broker-backed position set by symbol. This is a calculation over broker data, not an independent source of truth.

## Important boundary

The legacy portfolio application contains user-scoped portfolio models for longer-term portfolio management. This phase does not substitute those models for broker reality on the live trading portfolio page.

## Tests

`core/tests/test_portfolio_positions_contract.py` verifies both pages start from a broker-connection state and contain no example trading/account values.

## Verification note

No GitHub Actions workflow run is exposed for the current branch/commit. Targeted repository test coverage has been added; full browser/backend/broker E2E remains part of Phase 19.
