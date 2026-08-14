# Phase 18 — Integration Checklist

The observability foundation is implemented, but telemetry should be wired into every production subsystem before deployment.

Required producers:
- Django request middleware -> request latency/status/trace id
- Trading engine -> lifecycle, rejected/failed executions
- Risk engine -> risk trips and blocked trades
- Broker adapters -> connect/auth/stream/order latency and failures
- WebSocket manager -> connection/reconnect state
- Celery/background workers -> task started/succeeded/failed/retried
- Backtesting -> job progress/failure
- AI inference -> model latency/errors
- Notifications -> delivery success/failure
- Database/cache -> connectivity and latency
- Scheduler -> missed/late jobs

Production recommendations:
- Use structured JSON logs.
- Propagate a trace/correlation ID through requests, jobs and trading events.
- Never log broker tokens, API secrets, credentials or sensitive user data.
- Send critical events to an external error/incident system.
- Add retention/partitioning policies for high-volume metrics/events.
- Add uptime checks outside the application process.
- Keep monitoring failures out of the critical trade-execution path.
