# Phase 18 — Monitoring & Observability

Added an operational monitoring layer and dashboard.

Page:
- `/monitoring/`

APIs:
- GET `/api/observability/dashboard/`
- POST `/api/observability/health/`
- POST `/api/observability/metrics/`
- POST `/api/observability/events/`
- GET `/api/observability/audit/`

Data domains:
- HealthCheck
- SystemMetric
- OperationalEvent
- AuditEvent

The dashboard surfaces:
- overall platform state
- healthy/degraded/down components
- critical/error event counts
- service latency
- trading-critical checks
- operational event feed
- system metrics
- audit activity

The model/service layer is intentionally generic so existing broker, trading engine, risk, Celery/worker, WebSocket and notification services can emit telemetry without coupling themselves to the UI.
