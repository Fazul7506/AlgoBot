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

## Repeatable infrastructure setup (safe by default)

From the repository root, run the source/configuration preflight and Wrangler bundle checks:

```sh
bash cloudflare/deploy-safe.sh --check
```

This check does not deploy or mutate Cloudflare resources. The opt-in `--apply` mode first verifies Cloudflare Queue API access, creates only missing Queue resources, and deploys the three Wrangler configurations with their checked-in activation flags set to `false`. It does not create or change secret values, enable live streaming/scheduling, enable execution recovery, or enable trading:

```sh
export CLOUDFLARE_ACCOUNT_ID="your-account-id"
export CLOUDFLARE_API_TOKEN="token-with-required-queue-and-worker-deployment-permissions"
bash cloudflare/deploy-safe.sh --apply
```

Use a least-privilege API token and verify the account before running `--apply`. Do not paste the token into chat, commit it, or enable flags as part of deployment. The script does not print the token or secret values. Queue consumer bindings, retry policies, DLQ destinations, Durable Object bindings/migrations, and cron triggers are applied from the version-controlled Wrangler configs. If deployment fails, keep all activation flags off and correct the reported resource/permission issue before retrying; the setup only creates queues that are missing and does not purge or delete queues.

### Secret and environment mapping

Configure values interactively with Wrangler after the initial disabled Worker deployment, then set the matching Django environment variable in Render. Never put real values in Wrangler `vars`, source files, logs, or this repository.

| Cloudflare Worker secret | Matching Render/Django environment |
|---|---|
| `CLOUDFLARE_MARKET_STREAM_TOKEN` on `algobot-market-stream` | `CLOUDFLARE_MARKET_STREAM_TOKEN` |
| `MARKET_STREAM_CONTROL_TOKEN` on `algobot-market-stream` | Worker-only control secret; no Render copy required |
| `ALGOBOT_TASK_DISPATCH_TOKEN` on `algobot-background-scheduler` | `CLOUDFLARE_TASK_DISPATCH_TOKEN` |
| `AI_TRAINING_WEBHOOK_TOKEN` on legacy dispatcher | `CLOUDFLARE_TRAINING_WEBHOOK_TOKEN` |

The scheduler URL and market endpoint URLs are non-secret config values in their respective Wrangler files. Before any activation, confirm that the public API domain resolves to the intended Render deployment and that each matching secret is present on both sides. Keep `CLOUDFLARE_SCHEDULER_ACTIVE=false`, `CLOUDFLARE_MARKET_STREAM_ACTIVE=false`, `ENABLE_EXECUTION_QUEUE_RECOVERY=false`, and live-trading/execution flags disabled until the separate validation and controlled-cutover steps are approved.

The preflight is intentionally a source/configuration check, not proof of live account state. After a disabled deployment, independently inspect the Cloudflare dashboard/API for Worker scripts, Queue consumers and DLQs, secret names (never values), cron triggers, Durable Object migrations, and R2 access. Do not retire the legacy dispatcher, Celery, or Render market stream until end-to-end parity and recovery checks pass.

