# AlgoBot AI training dispatcher — Cloudflare setup

This Worker is the legacy external retraining scheduler and queue consumer. The unified scheduler in `../background-scheduler/` now owns the AI schedule definitions and routes them through the common authenticated task-dispatch endpoint. The legacy schedule is gated off by default (`AI_TRAINING_DISPATCH_ACTIVE=false`) so both schedulers must not be active at once. Keep this consumer and its webhook until existing queue messages have drained and the cutover is verified. It does **not** run Python, scikit-learn, XGBoost or LightGBM. It sends an authenticated request to the AlgoBot Django service, which enqueues the existing Celery task. The Python Celery worker inside the AlgoBot runtime performs model training.

## Cloudflare resources

Created in the connected Cloudflare account:

- Worker: `algobot-ai-training-dispatcher`
- Queue: `algobot-ai-training`
- Dead-letter queue: `algobot-ai-training-dlq`
- Consumer: one message per batch, concurrency 1, five retries, 60-second retry delay

The Worker has a secret binding named `AI_TRAINING_WEBHOOK_TOKEN`. Never put this value in source control.

The legacy Worker retains its old four schedule definitions for reference, but its scheduled producer returns unless `AI_TRAINING_DISPATCH_ACTIVE=true`. The unified scheduler now emits the same training and external-signal task families through `algobot-background-tasks`. Existing deployed settings are not changed by a repository commit; verify live Worker variables and queue depth during cutover.

## Render webhook configuration

Set `CLOUDFLARE_TRAINING_WEBHOOK_TOKEN` on the AlgoBot Render service to the same secret value as the Cloudflare Worker secret. Do not paste the secret into chat, source control, or logs.

The webhook route added by PR #461 is:

`POST /api/internal/cloudflare/ai-training/`

It accepts only the bearer secret and a small JSON payload. It routes `scheduled_ai_training`, `ingest_sentiment`, and `ingest_orderbook` messages to their respective Celery tasks on the `celery` queue.

## Cloudflare R2 model storage

The application expects these Render environment variables:

- `CLOUDFLARE_R2_ACCOUNT_ID`
- `CLOUDFLARE_R2_ACCESS_KEY_ID`
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY`
- `CLOUDFLARE_R2_BUCKET`
- `AI_MODEL_SIGNING_KEY`
- Optional prefix: `AI_MODEL_PREFIX` (defaults to `algobot/models`)

The private bucket `algobot-model-artifacts` exists in the connected Cloudflare account and was verified empty at the last check. Create or confirm bucket-scoped S3 API credentials with Object Read & Write permissions and add the access key and secret to Render. Use a separate, high-entropy signing key for `AI_MODEL_SIGNING_KEY`; do not reuse the webhook token.

Model files are uploaded and downloaded with chunked streaming. Each artifact has a signed JSON manifest containing the exact ordered feature schema and installed package versions. SHA-256 and HMAC checks cover both the artifact bytes and manifest; verification happens before `joblib.load`.

## Operational boundary and free-tier limitation

Cloudflare Queues and Cron Triggers provide external scheduling and dispatch. Python model training remains on the existing Render Celery worker because a Cloudflare Worker is not a drop-in host for this Django/Python/scikit-learn training stack.

The Render supervisor in this branch starts Daphne, a Celery worker, Celery Beat, and the Deriv market stream in the same service. Cloudflare owns the external schedules and queue dispatch; the Celery worker executes Python tasks. Cloudflare Workers cannot execute this repository's Django/Python/scikit-learn training runtime. AI training and external-signal ingestion schedules are intentionally absent from Celery Beat to avoid duplicate scheduling.

The Blueprint is pinned to Render's existing free plan to avoid an automatic paid-plan upgrade. Free Render web services can spin down when idle and do not provide an always-on worker guarantee. This is suitable for a low-cost prototype/periodic wake-up design, but it is not a fully reliable 24/7 trading runtime. Do not claim continuous retraining or live stream uptime until the runtime's availability and broker-feed monitoring are proven.

Do not activate live retraining until R2 is enabled, the R2 variables/signing key are set, the webhook route is deployed to production, and the Celery broker/worker can be verified. Missing storage configuration intentionally causes training to fail closed rather than storing a champion model on ephemeral disk.


## External sentiment source configuration

Configure these Render variables:

- `AI_SENTIMENT_RSS_URLS`: comma-separated HTTPS RSS/Atom feed URLs.
- `AI_SENTIMENT_SYMBOL_KEYWORDS_JSON`: JSON object mapping exact AlgoBot market symbols to arrays of matching terms, for example `{"EURUSD":["EUR/USD","EURUSD"],"BTCUSD":["Bitcoin","BTC/USD"]}`.

RSS entries are scored with VADER and stored with their publication timestamp. Training uses only observations published at or before each candle timestamp; live inference uses recent persisted observations. No keyword mapping means no sentiment feature observations are invented.

## Level-2 order-book provider contract

Deriv tick/candle streams do not provide bid/ask depth quantities for the relevant instruments. `proposal_open_contract` is not an order-book endpoint. To calculate true depth imbalance, configure a provider that supports the same instruments and set:

- `ORDER_BOOK_API_URL`: HTTPS endpoint template containing `{symbol}`.
- `ORDER_BOOK_API_TOKEN`: optional bearer token.
- `ORDER_BOOK_SYMBOLS`: comma-separated AlgoBot symbols actually supported by that provider. Set this explicitly; otherwise AlgoBot will attempt every active/tradable symbol.

The endpoint must return JSON with non-empty `bids` and `asks` arrays, each containing `[price, quantity]` levels. AlgoBot validates the top ten levels, persists snapshots, and computes `(bid_volume - ask_volume) / (bid_volume + ask_volume)`. No candle-volume or quote-only substitute is used. Do not enable this feature for symbols unsupported by the chosen provider.
