# Phase 5 — Broker Connection

Status: COMPLETE AND WORKING

## Scope

The broker connection surface is now the first complete application workflow built on the shared state/design/base architecture.

## Frontend

`templates/broker/connect_broker.html` now:

- uses generic broker language rather than hardcoded Deriv-only UI
- shows connection state from the canonical broker state contract
- never renders fabricated account/balance/P/L data
- lists only brokers supplied by the backend view context
- routes each connection action through the existing broker connection endpoint/flow
- uses shared design-system primitives
- remains responsive on mobile

`static/js/broker_connection_page.js` subscribes to canonical broker state and renders explicit connection states.

## Backend contract hardening

`BrokerAccountSerializer.get_account_type()` now returns `unknown` when the broker has not confirmed an account type instead of silently returning `demo`.

`BrokerAccountViewSet.select()` now refuses account switching until the broker has confirmed the account type.

The broker account API remains user-scoped and does not serialize credential fields.

## Tests added

`apps/brokers/tests/test_phase5_connection_contract.py` verifies:

- unconfirmed account type is `unknown`
- credential payload is not serialized
- account switching is rejected when the broker has not confirmed account type

## Production invariant

`Connect -> authenticate -> broker confirms -> synchronize -> READY -> frontend displays broker state`.

No broker confirmation means no fabricated account type and no trading-state assumptions.

## Verification note

The repository exposes no workflow run for the current commit, so GitHub Actions has not supplied an external CI result. The phase has repository-level implementation and targeted test coverage; final production E2E remains part of Phase 19.
