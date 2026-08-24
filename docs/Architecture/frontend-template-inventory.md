# AlgoBot Frontend Template Inventory

This is the Phase 0 migration registry referenced by `FRONTEND_REFACTOR_MASTER.md`.

## Confirmed domains

base/shared; accounts; AI; analytics; automation; backtesting; broker/brokers; components; copy trading; dashboard; deployment; Deriv; developer; enterprise; indicators; market data; monitoring; notifications; portfolio; risk; SaaS; smart money; trading.

## Representative template surfaces

- `templates/base.html`
- `templates/core/` — authentication, dashboard, markets, strategies, trading, orders, positions, portfolio, signals, performance, settings, profile, system status and legal pages
- `templates/broker/` — broker marketplace, permissions, logs, health and connection
- `templates/brokers/` — dashboard, accounts, orders, positions, queue and broker list
- `templates/deriv/` — connect, authorize, tokens, dashboard, demo/real accounts and subscriptions
- `templates/trading/` — positions, contracts, quick trade, retry queue and trade detail
- `templates/portfolio/` — dashboard, reports and cash flow
- `templates/market_data/` — candles and symbols
- `templates/notifications/` — rules and templates
- `templates/monitoring/` — alerts and metrics
- `templates/risk/` — dashboard, exposure, drawdown, logs, rules, profile, correlation, kill switch, portfolio risk and margin monitor
- `templates/ai/` — dashboard, predictions, training jobs, model details/registry, regime, feature store, explainability, recommendations, ensembles and anomaly detection
- `templates/smart_money/` — BOS, MSS, CHOCH, alerts and heatmap
- `templates/developer/` — dashboard, sandbox, plugins, API keys, webhooks, tutorials and changelog
- `templates/saas/` — landing, auth, pricing, licenses, branding, admin portal, feature flags, custom domain, support, usage dashboard and customer portal
- `templates/copy_trading/` — reviews
- `templates/automation/` — workflow templates

## Migration rule

This inventory is a registry, not a completion claim. Each individual template/page receives the production gate when its implementation phase is reached.
