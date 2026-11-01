# AlgoBot background scheduler (standard Workers + Queues)

This project is a standard Cloudflare Worker and Cloudflare Queue consumer. It is not a Container and does not run a Python/Django/Celery runtime.

## Current migration boundary

- Cloudflare Cron Triggers replace the Celery Beat clock for the schedules listed in `src/index.js`.
- Cloudflare Queues provide buffering, retry, and a dead-letter queue.
- The authenticated Django dispatch endpoint enqueues the existing allowlisted Celery tasks. Therefore **a Celery execution worker is still required** until each Python task has been ported to a Worker-compatible implementation or another supported runtime.
- Execution queue recovery is deliberately gated by `ENABLE_EXECUTION_QUEUE_RECOVERY=true`. Do not enable it until the dispatch path has been validated against the production execution queue and duplicate-order protections.
- Cron Triggers have one-minute granularity, so a Durable Object alarm maintains the two former 30-second schedules. The alarm's 30-second slot is part of the dispatch idempotency key.
- The Worker defaults to disabled (`CLOUDFLARE_SCHEDULER_ACTIVE=false`). Provision queues and secrets, deploy it, verify the consumer and harmless task path, then explicitly enable it during cutover.

## Required resources and secrets

Create queues:
- `algobot-background-tasks`
- `algobot-background-tasks-dlq`

Set secret `ALGOBOT_TASK_DISPATCH_TOKEN` in Cloudflare and matching Django environment variable `CLOUDFLARE_TASK_DISPATCH_TOKEN` in Render. Keep secrets out of source control.

Deploy from this directory with Wrangler after queue creation and secret configuration. Do not enable execution queue recovery during initial smoke tests.

## Remaining full migration work

This scheduler only moves scheduling and buffering. Native Python tasks (Django ORM, Celery tasks, scikit-learn/XGBoost/LightGBM/TensorFlow) are not automatically executable inside standard JavaScript Workers. Each task needs a tested port before its Celery execution dependency can be removed. The Deriv market stream also needs a separate Worker/Durable Object implementation plus an authenticated, idempotent ingestion endpoint; do not stop the existing stream until parity tests pass.
