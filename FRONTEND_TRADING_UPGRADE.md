# AlgoBot frontend trading-first upgrade

Implemented:
- Replaced the generic enterprise placeholder page with a live backend-connected workspace shell.
- Added a real Trading Terminal at `/trading/` with symbol/timeframe selection, candle chart, market regime/structure, strategy signals, positions, recent orders, broker-account selection and order submission.
- Added authenticated UI pages for `/orders/`, `/positions/`, `/signals/`, and `/portfolio/`.
- Added live KPI loading for account balance, open positions, win rate and P/L.
- Added backend resource discovery links and module-aware workspaces across the existing template catalog.
- Added a UI kill-switch action wired to the risk backend.
- Updated navigation so users can reach trading, orders, positions, signals and portfolio directly.
- Improved responsive terminal/workspace styling.

Validation:
- JavaScript syntax checked successfully with Node.
- Python source modified in `core/views.py` and `deriv_platform/urls.py` was AST-parsed successfully.
- Django `manage.py check` could not run in the build environment because Django is not installed there. Run it inside the project's virtual environment before deployment.

Important:
- Live order submission remains governed by the existing backend `ExecutionEngine`, broker connection, broker account and risk controls.
- The frontend does not bypass broker authentication or backend validation.
