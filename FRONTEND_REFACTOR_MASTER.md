# AlgoBot Frontend Production Refactor Master Contract

Status: PHASE 1 COMPLETE AND WORKING
Branch: `refactor/frontend-production-foundation`
Base: `main` at `0061efc6dcf166cb5b13e52ac3c3e3e3bae94750`
Long-lived PR: `#17`

## Non-negotiable product invariant

The broker is the source of truth for broker-backed trading state.

`Broker -> Broker Adapter/Manager -> Django service/API -> REST/WebSocket -> Frontend state -> Template/Page -> User command -> Django -> Broker -> confirmed result -> Frontend state`

The frontend must never manufacture trading reality.

Before a broker connection is established, broker-backed UI must not show invented balances, equity, positions, orders, prices, P/L, account identity, or live status. After connection, those values must be traceable to backend/broker state.

## Page/template production gate

A page may advance only when all applicable checks pass:

- route/view renders successfully
- template inheritance is correct
- real backend data contract is identified
- broker dependency is identified
- no hardcoded trading/account/credential data remains
- loading, empty, error, no-broker, disconnected and reconnecting states are handled
- mutations travel through backend to broker and UI changes only from confirmed result/state
- REST/WebSocket lifecycle is correct
- permissions/authentication are enforced
- desktop/tablet/mobile behavior is acceptable
- keyboard/focus/accessibility behavior is acceptable
- no console/runtime errors are introduced
- automated checks/CI pass

Target: L5 Production. Foundational templates may reach L6 Reference before dependent pages are migrated.

## Refactor sequence

0. Repository/template inventory — COMPLETE
1. Frontend state/data architecture — COMPLETE AND WORKING
2. Credential and hardcoded-data elimination
3. Shared design system
4. `templates/base.html`
5. Broker connection
6. Dashboard
7. Portfolio/Positions
8. Orders
9. Trade history
10. Market/watchlist
11. Charts
12. Strategies
13. Automation
14. Workflow templates/builder
15. Notifications
16. Settings
17. Remaining operational/admin pages
18. Global consistency pass
19. Production E2E validation

## Phase 1 implementation

The canonical browser state contract is now available globally through `window.AlgoBotBrokerState` and is loaded from `templates/base.html`.

Supported lifecycle states:

`NO_BROKER`, `CONNECTING`, `CONNECTED`, `SYNCING`, `READY`, `DEGRADED`, `DISCONNECTED`, `RECONNECTING`, `ERROR`.

The state model owns broker/account, balances, positions, orders, trades, market, strategies, automation, notifications, timestamps and errors. It exposes subscription and transition APIs and emits `algobot:state-changed` events for page consumers.

The centralized frontend data contract is available through `window.AlgoBotFrontendData`. It provides the shared backend request wrapper, broker account retrieval, broker account synchronization, connected-broker guardrails, and broker-event normalization. It does not store or expose broker credentials.

`broker_state_bridge.js` connects the existing `live_broker_ui.js` account integration to the canonical state contract so the existing broker/account implementation remains the integration source while pages receive one consistent state surface.

No page is allowed to create a second competing global broker state model.

## Phase 1 exit criteria

- canonical broker lifecycle states implemented
- canonical broker-backed state container implemented
- centralized frontend data request contract implemented
- connected-broker guard implemented
- existing live broker account UI bridged into canonical state
- global base template loads the state contract in dependency order
- state contract contains no credentials or hardcoded trading values
- no second broker implementation introduced
- Phase 1 changes committed to the long-lived refactor branch
- Phase 1 recorded in PR #17

Phase 1 is complete and working at the repository-contract level. Runtime/CI verification remains a required gate wherever repository automation is available; no production page is considered complete until its own browser/backend/broker integration tests pass.

## Phase 0 inventory findings

The repository contains a large multi-domain template surface. Confirmed domains include:

- base / shared
- accounts
- AI
- analytics
- automation
- backtesting
- broker / brokers
- components
- copy trading
- dashboard
- deployment
- Deriv
- developer
- enterprise
- indicators
- market data
- monitoring
- notifications
- portfolio
- risk
- SaaS
- smart money
- trading

Confirmed template examples include:

- `templates/base.html`
- `templates/core/login.html`
- `templates/core/register.html`
- `templates/core/profile.html`
- `templates/core/settings.html`
- `templates/core/dashboard.html` where present by route/domain inventory
- `templates/core/orders.html`
- `templates/core/positions.html`
- `templates/core/portfolio.html`
- `templates/core/signals.html`
- `templates/core/performance.html`
- `templates/core/system_status.html`
- `templates/core/privacy.html`
- `templates/core/terms.html`
- `templates/core/cookies.html`
- `templates/core/contact.html`
- `templates/core/verify_email.html`
- `templates/core/reset_password.html`
- `templates/broker/brokers.html`
- `templates/broker/permissions.html`
- `templates/broker/broker_logs.html`
- `templates/broker/broker_health.html`
- `templates/brokers/dashboard.html`
- `templates/brokers/accounts.html`
- `templates/brokers/orders.html`
- `templates/brokers/positions.html`
- `templates/brokers/order_queue.html`
- `templates/brokers/broker_list.html`
- `templates/deriv/connect.html`
- `templates/deriv/authorize.html`
- `templates/deriv/tokens.html`
- `templates/deriv/dashboard.html`
- `templates/deriv/demo_accounts.html`
- `templates/deriv/real_accounts.html`
- `templates/deriv/subscriptions.html`
- `templates/trading/positions.html`
- `templates/trading/contracts.html`
- `templates/trading/quick_trade.html`
- `templates/trading/retry_queue.html`
- `templates/trading/trade_detail.html`
- `templates/portfolio/dashboard.html`
- `templates/portfolio/reports.html`
- `templates/portfolio/cashflow.html`
- `templates/market_data/candles.html`
- `templates/market_data/symbols.html`
- `templates/notifications/rules.html`
- `templates/notifications/templates.html`
- `templates/monitoring/alerts.html`
- `templates/monitoring/metrics.html`
- `templates/risk/dashboard.html`
- `templates/risk/exposure.html`
- `templates/risk/drawdown.html`
- `templates/risk/risk_logs.html`
- `templates/risk/risk_rules.html`
- `templates/risk/risk_profile.html`
- `templates/risk/correlation.html`
- `templates/risk/kill_switch.html`
- `templates/risk/portfolio_risk.html`
- `templates/risk/margin_monitor.html`
- `templates/ai/dashboard.html`
- `templates/ai/predictions.html`
- `templates/ai/training_jobs.html`
- `templates/ai/model_details.html`
- `templates/ai/model_registry.html`
- `templates/ai/market_regime.html`
- `templates/ai/feature_store.html`
- `templates/ai/explainability.html`
- `templates/ai/recommendations.html`
- `templates/ai/ensemble_models.html`
- `templates/ai/anomaly_detection.html`
- `templates/smart_money/bos.html`
- `templates/smart_money/mss.html`
- `templates/smart_money/choch.html`
- `templates/smart_money/alerts.html`
- `templates/smart_money/heatmap.html`
- `templates/developer/dashboard.html`
- `templates/developer/sandbox.html`
- `templates/developer/plugins.html`
- `templates/developer/api_keys.html`
- `templates/developer/webhooks.html`
- `templates/developer/tutorials.html`
- `templates/developer/changelog.html`
- `templates/saas/landing.html`
- `templates/saas/login.html`
- `templates/saas/signup.html`
- `templates/saas/pricing.html`
- `templates/saas/licenses.html`
- `templates/saas/branding.html`
- `templates/saas/admin_portal.html`
- `templates/saas/feature_flags.html`
- `templates/saas/custom_domain.html`
- `templates/saas/support_center.html`
- `templates/saas/usage_dashboard.html`
- `templates/saas/customer_portal.html`
- `templates/copy_trading/reviews.html`
- `templates/automation/workflow_templates.html`

The inventory is intentionally treated as a migration registry rather than a promise that every template has already been behaviorally audited. Each template will receive its own production gate when its phase is reached.

## Current base-template observations

`templates/base.html` already provides a shared authenticated shell, responsive navigation, global broker/account status hooks, toast handling, theme control, API timeout protection, and inclusion of `live_broker_ui.js`. These existing mechanisms are preserved as the starting point for Phase 4 rather than duplicated.

The current base also contains several inline/global behaviors and multiple global styles/scripts. Phase 4 will consolidate these carefully without breaking existing routes.

`static/js/live_broker_ui.js` already calls broker-account endpoints and renders connected account information. It must be treated as existing integration code to validate and harden, not as permission to create a second broker state architecture.
