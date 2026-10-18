# Redis command quota operations

AlgoBot shares the configured Redis endpoint between Django's cache, Channels, Celery's broker, and Celery's result backend. A change that appears small in one subsystem can affect live market data, WebSocket delivery, background jobs, rate limiting, and task recovery. Do not disable Redis or turn off those features as a quota workaround.

## Budget math

For a plan with 500,000 commands per month, a 30-day month averages about 16,700 commands/day, 694/hour, or 11.6/minute. These are budget averages, not safe burst limits. Use the actual quota/reset window shown in the Upstash console; do not assume that an over-quota database will recover immediately or that overage behavior is identical across plans.

Bandwidth and storage are separate metrics. Low bandwidth/storage with high command usage points toward command frequency, not necessarily oversized payloads.

## Production environment settings

Set secrets only in the hosting provider's environment configuration. Never commit or log `REDIS_URL`, passwords, or tokens.

- `USE_REDIS=true` enables the shared Redis cache and Redis-backed Channels layer.
- `REDIS_URL` must be the provider-issued endpoint; use its TLS scheme (commonly `rediss://`) when required by the provider.
- `REDIS_CACHE_MAX_CONNECTIONS` bounds Django's synchronous cache pool (default: `1`).
- `REDIS_CACHE_HEALTH_CHECK_INTERVAL` controls redis-py connection health checks (default: `30` seconds).
- `CELERY_BROKER_POOL_LIMIT` bounds Celery's broker connection pool (default: `1`).
- `CELERY_REDIS_MAX_CONNECTIONS` bounds Celery Redis transport pools (broker default: `2`, result backend default: `1`).
- `REDIS_CHANNEL_MAX_CONNECTIONS` bounds the Channels Redis pool per ASGI process (default: `2`).

Connection-pool limits protect the database's client budget; they do **not** reduce the number of Redis commands issued. Increasing these values is not a command-quota fix.

## Diagnose before changing behavior

1. Record the current Upstash command total/rate and its reset period before deployment. Record bandwidth and storage separately.
2. Identify command sources by subsystem: HTTP rate throttles, developer API middleware, market-data cache writes, Channels messages/groups, Celery broker/result/event traffic, and health/monitoring probes.
3. Compare equal-duration windows with similar traffic. Include the deployed commit, request/tick/task volume, and exact observation interval in the record.
4. Check that live tick timestamps remain fresh, WebSocket updates arrive, Celery queues drain and recover, and rate-limit behavior remains intact.
5. Recheck the Upstash dashboard after rollout and again after a representative load period. Do not mark the incident resolved from CI results alone.

## Safety rules

- Do not reduce market-data cache TTLs or suppress quote/candle updates without proving that API and WebSocket consumers remain fresh.
- Do not replace DRF's sliding-window throttles with a fixed-window limiter without explicitly testing burst behavior and authorization boundaries.
- Do not disable Celery task events, result storage, remote control, acknowledgements, or recovery until task consumers and operational recovery requirements are audited.
- Avoid repeated read-after-write probes when a successful write is sufficient for the specific health signal, but preserve a readiness check's documented dependency contract.
- Redis-failure fallbacks are process-local and cannot provide globally coordinated rate limiting. Treat them as degraded operation, not equivalent enforcement.
- Never run `FLUSHDB` or `FLUSHALL` as a quota remedy; they can destroy live broker/task state.

## Acceptance evidence

The incident is not resolved until the relevant tests and CI pass, a repeatable representative workload shows a measured command reduction, and production validation confirms that trading, fresh market data, WebSockets, Celery routing/recovery, and rate limits still work. Document before/after command counts and methodology in the incident issue.
