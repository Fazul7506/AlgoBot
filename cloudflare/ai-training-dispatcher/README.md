# AlgoBot AI training dispatcher — Cloudflare setup

This Worker owns the external retraining schedule and durable dispatch queue. It does **not** run Python, scikit-learn, XGBoost or LightGBM. It sends an authenticated request to the AlgoBot Django service, which enqueues the existing Celery task. The Python Celery worker inside the AlgoBot runtime performs model training.

## Cloudflare resources

Created in the connected Cloudflare account:

- Worker: `algobot-ai-training-dispatcher`
- Queue: `algobot-ai-training`
- Dead-letter queue: `algobot-ai-training-dlq`
- Consumer: one message per batch, concurrency 1, five retries, 60-second retry delay

The Worker has a secret binding named `AI_TRAINING_WEBHOOK_TOKEN`. Never put this value in source control.

The intended schedules are `15 */6 * * *` (every six hours) and `30 2 * * *` (daily at 02:30 UTC). They are deliberately **not active yet**. The current production API is still on `main`, while the authenticated webhook route exists on PR #461. Enabling the schedules before the production release would dispatch to a route that is not deployed. Activate the two schedules only after the production release, R2 setup, and worker verification.

## Render webhook configuration

Set `CLOUDFLARE_TRAINING_WEBHOOK_TOKEN` on the AlgoBot Render service to the same secret value as the Cloudflare Worker secret. Do not paste the secret into chat, source control, or logs.

The webhook route added by PR #461 is:

`POST /api/internal/cloudflare/ai-training/`

It accepts only the bearer secret and a small JSON payload. It validates the timeframe and accuracy threshold and enqueues `scheduled_ai_training` on Celery's `celery` queue.

## Cloudflare R2 model storage

The application expects these Render environment variables:

- `CLOUDFLARE_R2_ACCOUNT_ID`
- `CLOUDFLARE_R2_ACCESS_KEY_ID`
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY`
- `CLOUDFLARE_R2_BUCKET`
- `AI_MODEL_SIGNING_KEY`
- Optional prefix: `AI_MODEL_PREFIX` (defaults to `algobot/models`)

R2 is not enabled on the connected Cloudflare account yet. The Cloudflare API returned error 10042 asking for R2 to be enabled in the Dashboard. Enable R2, create a **private** bucket, and create bucket-scoped S3 API credentials before adding these values to Render. Use a separate, high-entropy signing key for `AI_MODEL_SIGNING_KEY`; do not reuse the webhook token.

Model files are uploaded and downloaded with chunked streaming. Each artifact has a signed JSON manifest containing the exact ordered feature schema and installed package versions. SHA-256 and HMAC checks cover both the artifact bytes and manifest; verification happens before `joblib.load`.

## Operational boundary and free-tier limitation

Cloudflare Queues and Cron Triggers provide external scheduling and dispatch. Python model training remains on the existing Render Celery worker because a Cloudflare Worker is not a drop-in host for this Django/Python/scikit-learn training stack.

The Render supervisor in this branch starts Daphne, a Celery worker, Celery Beat, and the Deriv market stream in the same service. AI retraining schedules are intentionally removed from Celery Beat to avoid duplicate scheduling.

The Blueprint is pinned to Render's existing free plan to avoid an automatic paid-plan upgrade. Free Render web services can spin down when idle and do not provide an always-on worker guarantee. This is suitable for a low-cost prototype/periodic wake-up design, but it is not a fully reliable 24/7 trading runtime. Do not claim continuous retraining or live stream uptime until the runtime's availability and broker-feed monitoring are proven.

Do not activate live retraining until R2 is enabled, the R2 variables/signing key are set, the webhook route is deployed to production, and the Celery broker/worker can be verified. Missing storage configuration intentionally causes training to fail closed rather than storing a champion model on ephemeral disk.
