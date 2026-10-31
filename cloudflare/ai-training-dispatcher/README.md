# AlgoBot AI training dispatcher — Cloudflare setup

This Worker owns the retraining schedule and durable dispatch queue. It does **not** run Python, scikit-learn, XGBoost or LightGBM. It sends an authenticated request to the AlgoBot Django service, which enqueues the existing Celery task. The Celery worker inside the existing AlgoBot runtime performs training.

## Cloudflare resources

Created in the connected Cloudflare account:

- Worker: `algobot-ai-training-dispatcher`
- Queue: `algobot-ai-training`
- Dead-letter queue: `algobot-ai-training-dlq`
- Consumer: one message per batch, concurrency 1, five retries, 60-second retry delay
- Cron: `15 */6 * * *` and `30 2 * * *`

The Worker uses a secret binding named `AI_TRAINING_WEBHOOK_TOKEN`. Do not put this value in source control.

## Render webhook configuration

Set `CLOUDFLARE_TRAINING_WEBHOOK_TOKEN` on the AlgoBot Render web service to the same secret value as the Worker secret. The PR #461 preview service has been configured with the matching value. Production must receive the same setting only after the PR has passed validation and is approved for deployment.

The webhook route is:

`POST /api/internal/cloudflare/ai-training/`

It accepts only the bearer secret and a small JSON payload. It validates the timeframe and accuracy threshold and enqueues `scheduled_ai_training` on Celery's `celery` queue.

## Cloudflare R2 model storage

The application now expects these Render environment variables:

- `CLOUDFLARE_R2_ACCOUNT_ID`
- `CLOUDFLARE_R2_ACCESS_KEY_ID`
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY`
- `CLOUDFLARE_R2_BUCKET`
- `AI_MODEL_SIGNING_KEY`
- Optional prefix: `AI_MODEL_PREFIX` (defaults to `algobot/models`)

R2 is not enabled on the connected Cloudflare account yet. The Cloudflare API returned error 10042 asking for R2 to be enabled in the Dashboard. Enable R2, create a **private** bucket, and create bucket-scoped S3 API credentials before adding these values to Render. Use a separate, high-entropy signing key for `AI_MODEL_SIGNING_KEY`; do not reuse the webhook token.

Each artifact is stored with a JSON manifest containing the exact ordered feature schema and package versions. SHA-256 and HMAC checks cover both the artifact bytes and manifest; verification happens before `joblib.load`.

## Operational boundary

Cloudflare Queues are the external scheduler/dispatch layer. Python model training remains on the existing Render Celery worker because Cloudflare Workers are not a drop-in host for this Django/Python/scikit-learn training stack. The current Render supervisor runs Daphne, Celery worker, Celery Beat and the Deriv stream in one service; AI retraining schedules were removed from Celery Beat to avoid duplicate scheduling.

Do not enable live retraining until R2 is enabled and the R2 variables/signing key are set. Missing storage configuration intentionally causes training to fail closed rather than storing a champion model on ephemeral disk.
