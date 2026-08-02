# Observability Platform

Phase 11 adds a centralized observability platform for AlgoBot. It covers system, broker, trading, strategy, AI, risk, infrastructure, application, performance, audit, log, metric, trace, alert, incident, notification, and self-healing workflows.

## Capabilities

- Real-time health snapshots for application, database, Redis/cache, Celery, WebSocket, broker, trading, strategy, AI, risk, backtesting, API, authentication, storage, and cache services.
- Central models for system health, broker health, alerts, audit logs, metrics, incidents, log entries, and trace spans.
- API endpoints under `/api/monitoring/`, `/api/alerts/`, `/api/incidents/`, `/api/metrics/`, `/api/audit/`, and `/api/logs/`.
- WebSocket event contracts for health, alert, incident, broker, strategy, AI, risk, infrastructure, database, and recovery events.
- Self-healing actions for Celery restarts, broker and websocket reconnects, cache flushes, queue cleanup, failed-task retries, monitoring restarts, strategy reloads, and AI model reloads.
- Integration-friendly architecture for Prometheus, Grafana, OpenTelemetry, ELK, Loki, Jaeger, Sentry, Redis Insight, PostgreSQL monitoring, and Docker monitoring.

## Operations

Use the monitoring services from `apps.monitoring.services` in request handlers, background jobs, and trading-safe asynchronous workers. The implementation is intentionally non-blocking for trading paths: failures are recorded as alerts and log entries instead of raising into execution flows.
