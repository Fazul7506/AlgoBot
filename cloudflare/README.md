# AlgoBot Cloudflare background migration

This migration uses standard Cloudflare Workers, Queues, and Durable Objects. It does not use Cloudflare Containers.

## Components

- `background-scheduler/`: unified Cron Triggers, a Durable Object alarm for the 30-second schedules, and Queue dispatch for scheduled Django/Celery jobs, including AI training, sentiment, and order-book ingestion.
- `ai-training-dispatcher/`: legacy queue consumer retained only to drain/retire its existing queue safely; its schedule defaults off in source. Do not run both schedulers at once.
- `market-stream/`: Durable Object for Deriv WebSocket connectivity and a Queue for tick ingestion.

## Important execution boundary

The scheduler endpoint still publishes Python tasks to the existing Celery queue. It does not make Django ORM, Python dependencies, or native ML libraries run inside JavaScript Workers. **Do not remove the Celery execution worker yet.** The Celery worker migration remains incomplete until each Python task is ported to a tested Worker-compatible implementation or a different supported Python runtime is retained.

## Production cutover sequence

1. Keep Render's web-only Daphne start command unchanged.
2. Create the named queues and configure secrets in Cloudflare; configure matching Django secrets in Render. The unified scheduler and market stream default to disabled (`CLOUDFLARE_SCHEDULER_ACTIVE=false`, `CLOUDFLARE_MARKET_STREAM_ACTIVE=false`); the legacy AI dispatcher schedule defaults to disabled (`AI_TRAINING_DISPATCH_ACTIVE=false`).
3. Deploy and smoke-test the task-dispatch endpoint using harmless allowlisted tasks, including AI schedule payloads.
4. Deploy the background scheduler with activation off. Verify logs and queue/consumer health, then explicitly disable the legacy AI dispatcher schedule and enable the unified scheduler together during a controlled cutover. Verify each schedule fires once before disabling Celery Beat. Do not enable execution queue recovery until duplicate-order protection and the task path are verified.
5. Deploy the market stream alongside the existing Render stream and compare tick freshness, candles, snapshots, and Channels fan-out. The Worker serializes queue writes and closes the upstream socket when its bounded pending-write buffer reaches its limit.
6. Stop the Render market-stream process only after parity and reconnect tests pass.
7. Migrate Celery task execution individually; only then can the Celery worker be removed.

No production service, secret, queue, cron, or deployment is changed by these source files alone.
