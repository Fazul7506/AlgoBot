# AlgoBot Cloudflare background migration

This migration uses standard Cloudflare Workers, Queues, and Durable Objects. It does not use Cloudflare Containers.

## Components

- `ai-training-dispatcher/`: existing training/sentiment/orderbook queue dispatcher.
- `background-scheduler/`: Cron Triggers, a Durable Object alarm for the 30-second schedules, and Queue dispatch for scheduled Django/Celery jobs.
- `market-stream/`: Durable Object for Deriv WebSocket connectivity and a Queue for tick ingestion.

## Important execution boundary

The scheduler endpoint still publishes Python tasks to the existing Celery queue. It does not make Django ORM, Python dependencies, or native ML libraries run inside JavaScript Workers. **Do not remove the Celery execution worker yet.** The Celery worker migration remains incomplete until each Python task is ported to a tested Worker-compatible implementation or a different supported Python runtime is retained.

## Production cutover sequence

1. Keep Render's web-only Daphne start command unchanged.
2. Create the named queues and configure secrets in Cloudflare; configure matching Django secrets in Render. Both Workers default to disabled (`CLOUDFLARE_SCHEDULER_ACTIVE=false`, `CLOUDFLARE_MARKET_STREAM_ACTIVE=false`).
3. Deploy and smoke-test the task-dispatch endpoint using a harmless allowlisted task.
4. Deploy the background scheduler. Verify logs and queue/consumer health before setting Render's `CLOUDFLARE_SCHEDULER_ACTIVE=true` to disable Celery Beat. Do not enable execution queue recovery until duplicate-order protection and the task path are verified.
5. Deploy the market stream alongside the existing Render stream and compare tick freshness, candles, snapshots, and Channels fan-out.
6. Stop the Render market-stream process only after parity and reconnect tests pass.
7. Migrate Celery task execution individually; only then can the Celery worker be removed.

No production service, secret, queue, cron, or deployment is changed by these source files alone.
