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
5. Deploy the market stream alongside the existing Render stream and compare tick freshness, candles, snapshots, and Channels fan-out. The Worker batches the documented Deriv symbol-array subscription, validates tick timestamps, drops stale ticks, retries transient Queue writes, and closes the upstream socket when its bounded pending-write buffer reaches its limit. Permanent Django payload rejections are preserved in the market-tick DLQ.
6. Stop the Render market-stream process only after parity and reconnect tests pass.
7. Migrate Celery task execution individually; only then can the Celery worker be removed.

No production service, secret, queue, cron, or deployment is changed by these source files alone.
## Queue failure visibility and operator alerts

Both unified queues now have automatic retry-to-DLQ configuration and explicitly route permanent Django 400/413/422 rejections into the matching DLQ. Transient transport, authentication, cache, and broker errors remain retryable; do not acknowledge them as successful dispatches.

For production observability, configure Cloudflare Notifications for:
- a non-empty algobot-market-ticks-dlq or algobot-background-tasks-dlq;
- sustained queue backlog / oldest-message age;
- Worker errors and Durable Object connection failures.

The DLQ queues intentionally have no consumer so failed payloads remain inspectable. Do not attach a consumer that automatically acknowledges and discards them. The Django side emits structured warnings for market-data degradation and model-performance degradation; use the existing Sentry/notification credentials to route these logs to an operator channel during the validation phase.

## AI lifecycle hooks

- A newly created M1 tick-stream candle closes the previous M1 candle and enqueues process_closed_candle; this builds the same ordered feature contract and writes a prediction plus a risk-gated recommendation, without placing an order.
- resolve_prediction_outcomes labels matured predictions from persisted canonical market candles and records model identity/version with the outcome.
- check_model_degradation groups resolved outcomes by the model identity/version persisted with each prediction. A degraded model can request retraining no more than once per timeframe per six hours.
- Model promotion compares the candidate against the current champion across algorithms. rollback_champion_model is an explicit operator-triggered Celery task and only restores a persisted model that passed the saved accuracy and profitability gates.

All these are source-level implementations. They remain inactive for Cloudflare scheduling/market streaming until the matching production secrets and activation flags are deliberately configured.

