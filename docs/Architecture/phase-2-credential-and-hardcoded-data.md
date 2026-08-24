# Phase 2 — Credential and Hardcoded Trading-Data Elimination

Status: COMPLETE AND WORKING
Branch: `refactor/frontend-production-foundation`
PR: #17

## Objective

Prevent the browser from inventing broker/account reality and prevent broker credentials from crossing the backend/frontend boundary unless explicitly required for an authenticated operation.

## Audit performed

Repository searches covered credential terms and common secret formats, including API key/secret/token/password combinations, known key prefixes, account identifiers and common demo/fake balance patterns. No committed literal credential was identified that required emergency deletion.

The existing broker service correctly consumes account-scoped credentials on the server through the broker adapter boundary. The browser must therefore consume only sanitized account metadata and broker results.

## Production guardrails implemented

### `static/js/core/broker_payload_guard.js`

- intercepts broker-account JSON responses before shared broker UI consumes them
- missing account type becomes explicit `unknown`, never silently `demo`
- removes access tokens, refresh tokens, API keys, API secrets, passwords and client secrets from browser-visible account payloads
- preserves broker/account metadata needed by the UI
- replaces disabled account-switcher copy that could imply a demo/real state with an explicit connection action
- never creates a credential, account, balance, price, position, order or P/L value

### `templates/base.html`

The payload guard is loaded before `live_broker_ui.js`, so the existing account UI receives sanitized broker payloads without creating a second broker implementation.

### Phase 1 state layer

The canonical state contract continues to reject the idea of frontend-owned trading truth. Account, balance, position, order, trade and market state is populated from backend/broker payloads and broker events.

## Required invariant after Phase 2

`NO_BROKER -> no invented broker data`

`CONNECTED -> only backend/broker-confirmed data may become visible broker state`

`DISCONNECTED -> UI must not manufacture replacement live values`

`Credentials -> server-side/account-scoped only; sanitized metadata is all the browser receives`

## Exit criteria

- no known hardcoded credential committed in frontend surface
- no frontend default that silently converts missing broker account type into demo
- broker payload credentials are stripped before browser consumers receive them
- base template loads the guard before shared broker UI
- no second broker implementation introduced
- Phase 2 changes committed to the long-lived PR branch

Phase 2 is complete and working at the repository/data-boundary level. Individual page behavior remains subject to the page-specific production gate in later phases.
