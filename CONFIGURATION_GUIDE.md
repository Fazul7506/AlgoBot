# AlgoBot Enterprise Configuration Guide

This guide documents every owner-managed environment variable discovered in the Django settings, broker, notification, payment, AI, Celery, Redis, and deployment configuration paths. Do not commit real secrets; copy `.env.example` to `.env` and fill values locally or in your production secret manager.

## Manual secrets to generate

- `SECRET_KEY` / `DJANGO_SECRET_KEY`: long random Django signing key.
- `CREDENTIALS_ENCRYPTION_KEY`: long random encryption passphrase/key for stored broker credentials.
- `STRIPE_WEBHOOK_SECRET`: obtained from Stripe webhook endpoint configuration.
- `EMAIL_PASSWORD`: SMTP or provider application password when SMTP is enabled.

## API keys to obtain manually

- `DERIV_APP_ID` / `DERIV_OAUTH_CLIENT_ID`: Deriv OAuth application identifier.
- `DERIV_API_TOKEN`: Deriv API token for broker operations that need direct token access.
- `STRIPE_SECRET_KEY` / `STRIPE_API_KEY`: Stripe secret API key for billing.
- `BREVO_API_KEY`: Brevo transactional email API key if Brevo notifications are used.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token if Telegram alerts are enabled.
- `OPENAI_API_KEY`: OpenAI API key if AI features require hosted model access.
- `SENTRY_DSN`: Sentry project DSN if error monitoring is enabled.

## External accounts to create before production

- Deriv developer application and production trading account.
- PostgreSQL database service.
- Redis service for cache, Celery, and channel-like realtime workloads.
- SMTP or Brevo email provider account.
- Stripe account, product prices, and webhook endpoint.
- Telegram bot and target chat, if Telegram alerts are enabled.
- OpenAI account, if hosted AI inference is enabled.
- Sentry project, if production error telemetry is enabled.

## Production blockers

Production settings now fail fast when these critical values are missing: `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL` or complete `POSTGRES_*`, `REDIS_URL`, `BASE_URL`, `DERIV_APP_ID`, and `DERIV_REDIRECT_URI`.

## Variables

| Variable Name | Purpose | Required | Safe Default | Example Format | Where Used | Secret | Development | Testing | Production |
|---|---|---:|---|---|---|---:|---|---|---|
| `SECRET_KEY` | Django and JWT signing key. | Yes | Dev-only insecure fallback | `change-me-long-random` | Django settings, Simple JWT | Yes | Required for realistic local sessions | Can use test value | Required |
| `DJANGO_SECRET_KEY` | Backward-compatible alias for `SECRET_KEY`. | No | Empty | `change-me-long-random` | Django settings fallback | Yes | Optional | Optional | Optional |
| `DEBUG` | Enables Django debug mode. | No | `true` in development | `true` / `false` | Django settings | No | Usually `true` | Usually `false` | Must be `false` |
| `DJANGO_DEBUG` | Backward-compatible alias for `DEBUG`. | No | Empty | `true` / `false` | Django settings fallback | No | Optional | Optional | Optional |
| `ALLOWED_HOSTS` | Comma-separated hosts accepted by Django. | Yes | `127.0.0.1,localhost,testserver` | `app.example.com,www.example.com` | Django host validation | No | Local hosts | `testserver` | Required |
| `BASE_URL` | Public application origin for callbacks and links. | Yes | `http://127.0.0.1:8000` | `https://app.example.com` | OAuth redirects, links | No | Local URL | Test URL | Required |
| `TIME_ZONE` | Django application timezone. | No | `Africa/Nairobi` | `UTC` | Django settings | No | Optional | Optional | Set intentionally |
| `DATABASE_URL` | Full PostgreSQL connection URL. | Production | Empty | `postgres://user:pass@host:5432/db` | Database settings | Yes | Optional | Optional | Recommended/required alternative |
| `USE_POSTGRES` | Enables PostgreSQL settings when no `DATABASE_URL` is supplied. | No | `false` unless URL set | `true` / `false` | Database settings | No | Optional | Optional | Usually `true` |
| `POSTGRES_DB` | PostgreSQL database name. | If using parts | `deriv_platform` | `algobot` | Database settings | No | Optional | Optional | Required if no URL |
| `POSTGRES_USER` | PostgreSQL username. | If using parts | `postgres` | `algobot_user` | Database settings | No | Optional | Optional | Required if no URL |
| `POSTGRES_PASSWORD` | PostgreSQL password. | If using parts | Empty | *(secret)* | Database settings | Yes | Optional | Optional | Required if no URL |
| `POSTGRES_HOST` | PostgreSQL host. | If using parts | `localhost` | `db.example.internal` | Database settings | No | Optional | Optional | Required if no URL |
| `POSTGRES_PORT` | PostgreSQL port. | If using parts | `5432` | `5432` | Database settings | No | Optional | Optional | Required if no URL |
| `REDIS_URL` | Redis URL for cache and Celery defaults. | Production | `redis://localhost:6379/0` | `redis://:pass@host:6379/0` | Cache and Celery settings | Maybe | Local Redis | Optional/eager tasks | Required |
| `USE_REDIS` | Enables Redis cache backend. | No | `false` | `true` / `false` | Cache settings | No | Optional | Optional | Recommended |
| `CELERY_BROKER_URL` | Celery broker URL. | If Celery enabled | `REDIS_URL` | `redis://host:6379/1` | Celery settings | Maybe | Optional | Usually eager | Required if workers run |
| `CELERY_RESULT_BACKEND` | Celery result backend URL. | If Celery enabled | `REDIS_URL` | `redis://host:6379/2` | Celery settings | Maybe | Optional | Usually eager | Required if workers run |
| `USE_CELERY` | Enables Celery-backed task dispatch. | No | `true` | `true` / `false` | Task dispatch | No | Optional | `false`/eager acceptable | Set intentionally |
| `DERIV_APP_ID` | Deriv application ID for OAuth/WebSocket. | Production | Empty | `12345` | Deriv OAuth and WebSocket | No | Required for Deriv testing | Optional | Required |
| `DERIV_OAUTH_CLIENT_ID` | Backward-compatible alias for `DERIV_APP_ID`. | No | Empty | `12345` | Deriv OAuth fallback | No | Optional | Optional | Optional |
| `DERIV_API_TOKEN` | Deriv API authentication token. | If direct broker access enabled | Empty | *(secret)* | Trading and broker services | Yes | Optional | Optional | Required for live direct API use |
| `DERIV_REDIRECT_URI` | Deriv OAuth callback URL. | Production | `${BASE_URL}/callback` | `https://app.example.com/callback` | Deriv OAuth | No | Local callback | Optional | Required |
| `DERIV_API_BASE` | Deriv REST API base URL. | No | `https://api.deriv.com` | `https://api.deriv.com` | Deriv client | No | Default OK | Default OK | Default OK |
| `DEFAULT_FROM_EMAIL` | Default sender address. | If email enabled | `noreply@example.com` | `noreply@example.com` | Email tasks, auth emails | No | Optional | Optional | Required for email |
| `EMAIL_BACKEND` | Django email backend path. | No | Console backend | `django.core.mail.backends.smtp.EmailBackend` | Email settings | No | Console OK | Locmem OK | SMTP/provider backend |
| `EMAIL_HOST` | SMTP host. | If SMTP enabled | Empty | `smtp.example.com` | Email settings | No | Optional | Optional | Required for SMTP |
| `EMAIL_PORT` | SMTP port. | If SMTP enabled | Empty/`587` example | `587` | Email settings | No | Optional | Optional | Required for SMTP |
| `EMAIL_USER` | SMTP username. | If SMTP enabled | Empty | `apikey` or email | Email settings | Maybe | Optional | Optional | Required for SMTP auth |
| `EMAIL_PASSWORD` | SMTP password. | If SMTP enabled | Empty | *(secret)* | Email settings | Yes | Optional | Optional | Required for SMTP auth |
| `BREVO_API_KEY` | Brevo email API key. | If Brevo enabled | Empty | *(secret)* | Notification service | Yes | Optional | Optional | Required for Brevo |
| `BREVO_SENDER_EMAIL` | Brevo sender email. | If Brevo enabled | `DEFAULT_FROM_EMAIL` | `alerts@example.com` | Notification service | No | Optional | Optional | Required for Brevo |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token. | If Telegram enabled | Empty | *(secret)* | Notification service | Yes | Optional | Optional | Required for Telegram |
| `TELEGRAM_CHAT_ID` | Telegram target chat ID. | If Telegram enabled | Empty | `-1001234567890` | Notification service | No | Optional | Optional | Required for Telegram |
| `PAYMENT_PROVIDER` | Billing provider selector. | No | `stripe` | `stripe` | Payment service | No | Optional | Optional | Set intentionally |
| `STRIPE_SECRET_KEY` | Stripe secret API key. | If billing enabled | Empty | *(secret)* | Payment service | Yes | Optional | Optional | Required for billing |
| `STRIPE_API_KEY` | Legacy alias for `STRIPE_SECRET_KEY`. | No | Empty | *(secret)* | Payment service fallback | Yes | Optional | Optional | Optional |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret. | If billing enabled | Empty | *(secret)* | Payment webhook | Yes | Optional | Optional | Required for billing webhooks |
| `OPENAI_API_KEY` | OpenAI API key for hosted AI features. | If hosted AI enabled | Empty | *(secret)* | AI settings | Yes | Optional | Optional | Required for hosted AI |
| `SENTRY_DSN` | Sentry telemetry DSN. | No | Empty | `https://key@sentry.io/project` | Logging/monitoring settings | Maybe | Optional | Optional | Recommended |
| `CREDENTIALS_ENCRYPTION_KEY` | Key material for encrypting stored broker credentials. | Production | Empty | *(secret)* | Credential encryption service | Yes | Optional for demo | Optional | Required before storing live credentials |
| `AUDIT_LOG_ENABLED` | Enables audit middleware/service behavior. | No | `true` | `true` / `false` | Security/audit settings | No | Usually `true` | Optional | Required/recommended `true` |
| `TWO_FACTOR_ENABLED` | Enables two-factor authentication features. | No | `true` | `true` / `false` | Security settings | No | Optional | Optional | Recommended `true` |
| `TWO_FACTOR_ISSUER` | Issuer label for two-factor tokens. | No | `DerivBot` | `AlgoBot` | Security settings | No | Optional | Optional | Set to product name |
| `SESSION_COOKIE_SECURE` | Sends session cookies only over HTTPS. | Production | `false` | `true` | Security settings | No | `false` OK | `false` OK | Required `true` |
| `CSRF_COOKIE_SECURE` | Sends CSRF cookies only over HTTPS. | Production | `false` | `true` | Security settings | No | `false` OK | `false` OK | Required `true` |
| `SESSION_COOKIE_SAMESITE` | Session cookie SameSite policy. | No | `Lax` | `Lax` | Security settings | No | Default OK | Default OK | Set intentionally |
| `CSRF_COOKIE_SAMESITE` | CSRF cookie SameSite policy. | No | `Lax` | `Lax` | Security settings | No | Default OK | Default OK | Set intentionally |

## Optional integrations

- **Brevo email:** `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, plus `DEFAULT_FROM_EMAIL`.
- **SMTP email:** `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWORD`, `DEFAULT_FROM_EMAIL`.
- **Telegram alerts:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- **Stripe billing:** `PAYMENT_PROVIDER`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.
- **OpenAI-backed AI features:** `OPENAI_API_KEY`.
- **Sentry monitoring:** `SENTRY_DSN`.
- **Redis cache/Celery:** `REDIS_URL`, `USE_REDIS`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `USE_CELERY`.
