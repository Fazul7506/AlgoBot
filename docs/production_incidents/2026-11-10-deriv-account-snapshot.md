# Deriv account switching and dashboard snapshot incident — 2026-11-10

## Production reproduction

Environment: `https://algobot.dpdns.org/dashboard/`

The owner supplied a mobile screenshot and dashboard capture showing:

- The server/browser still displays DEMO account `DOT90349003` as selected.
- The displayed DEMO balance is `$5,902.30` and is explicitly labelled `Stale broker snapshot`.
- Attempting to switch to REAL account `ROT91451760` returns: `The selected account snapshot could not be verified. Your previous account remains selected.`
- The dashboard reports stale broker state, no market snapshot, positions stuck at `Loading positions…`, and no recent orders, signals, or backend activity.
- Equity and available margin display `$0.00` before a verified snapshot. These are intentional initial placeholders, not fabricated values.

## Acceptance contract

1. A successful DEMO↔REAL switch must establish the exact requested account's connection and obtain its authoritative broker snapshot before changing the server-side selected-account session.
2. A failed switch must retain the previous confirmed account and must never label the requested account as selected.
3. A successful switch must refresh all account-scoped dashboard, terminal, positions, orders, and market-data consumers against the same server-confirmed account. No response from an older in-flight request may overwrite the newly selected account.
4. Snapshot state must distinguish loading, fresh, stale, unavailable, and genuinely empty backend results. Positions must leave loading state on both success and failure, with retryable/actionable failure feedback.
5. Market snapshots, orders, positions, signals, and activity must come from their real backend sources. Do not invent records or replace unavailable data with demo fixtures.
6. Preserve the initial zero equity/margin placeholders; replace them only when authoritative broker values are received.
7. Preserve account ownership, authentication/session/JWT/CSRF checks, credential handling, explicit DEMO/REAL isolation, plan/risk gates, and execution safeguards.
8. Add behavioral regression tests for the production reproduction and adjacent success/failure/concurrency cases. Run the full relevant CI and Production Validation workflows; do not weaken or skip checks.

This document records the owner-provided reproduction only. It is not evidence that the incident has been fixed.
