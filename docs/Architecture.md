# Architecture

AlgoBot is a modular Django trading platform. Core dependencies flow from market data, indicators, strategies, validation, risk, sizing, execution, broker adapters, trade lifecycle, portfolio analytics, and dashboards. The project preserves reusable apps under `apps/` and legacy domain modules under `trading/` while adding production seams for observability, health checks, and analytics.
