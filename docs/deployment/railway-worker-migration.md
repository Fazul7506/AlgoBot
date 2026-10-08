# Railway Worker Deployment and Oracle Handoff

## Purpose

AlgoBot keeps its existing Render web/API service while the four long-running background roles are moved to Railway during the temporary Railway trial:

1. **AlgoBot-Worker** — general Celery queue `celery`
2. **AlgoBot-Beat** — Celery Beat scheduler; exactly one instance
3. **AlgoBot-MarketData** — isolated `market_data` Celery queue
4. **AlgoBot-LiveMarketStream** — long-running live market stream

The worker commands are implemented in:

- `deploy/railway/general-worker.sh`
- `deploy/railway/beat.sh`
- `deploy/railway/market-data-worker.sh`
- `deploy/railway/live-market-stream.sh`

These scripts intentionally preserve the worker commands already used by `render.yaml`. No application/business logic is moved into Railway-specific code.

The general worker is the sole Railway worker entrypoint responsible for applying Django migrations. The other long-running processes intentionally do not run migrations at startup, preventing several workers from competing for Supabase connections during a rollout.

## Important migration rule

Do **not** remove the existing Render worker services until all four Railway services are deployed and their logs have been validated.

The safe sequence is:

**Render workers → Railway workers → validate → stop/remove Render workers → later Oracle workers**

This avoids a period in which neither worker platform is running.

## Railway project layout

Create one Railway project with these services:

- `AlgoBot-Worker`
- `AlgoBot-Beat`
- `AlgoBot-MarketData`
- `AlgoBot-LiveMarketStream`

Use the GitHub repository:

`Fazul7506/AlgoBot`

and branch:

`main`

Connect all four services to the same repository. Railway supports GitHub autodeploys from a selected branch.

### Recommended Railway region

Choose the Railway region geographically closest to the majority of AlgoBot's external dependencies and the existing Render database where practical. Keep all four worker services in the same Railway region.

## Start commands

In each Railway service, set **Custom Start Command** as follows.

### AlgoBot-Worker

```
sh deploy/railway/general-worker.sh
```

### AlgoBot-Beat

```
sh deploy/railway/beat.sh
```

### AlgoBot-MarketData

```
sh deploy/railway/market-data-worker.sh
```

### AlgoBot-LiveMarketStream

```
sh deploy/railway/live-market-stream.sh
```

Do not run Beat inside the normal Celery worker, and do not merge the live market stream into a Celery worker. Their current process separation is intentional.

## Railway environment variables

The workers need the same production infrastructure credentials as the current Render workers.

### Required core variables

Set these on all four worker services:

```
DJANGO_ENV=production
SECRET_KEY=<same production secret used by AlgoBot>
DATABASE_URL=<production PostgreSQL connection URL>
REDIS_URL=<production Redis connection URL>
USE_REDIS=true
USE_CELERY=true
CELERY_BROKER_URL=<same Redis URL>
CELERY_RESULT_BACKEND=<same Redis URL>
```

The production settings explicitly require a real `SECRET_KEY`, Redis, and a database connection.

### Celery reliability variables

For the Celery worker services:

```
CELERY_WORKER_BROKER_RETRY=true
CELERY_WORKER_RETRY_ON_STARTUP=true
```

### Trading / market-data variables

Copy the **existing production values** for the Deriv and broker integrations from the current deployment. Do not invent replacement values.

At minimum, review:

```
DERIV_OAUTH_CLIENT_ID
DERIV_OAUTH_CLIENT_SECRET
DERIV_OAUTH_SCOPE
DERIV_APP_ID
DERIV_API_TOKEN
DERIV_API_BASE_URL
DERIV_OPTIONS_ACCOUNTS_URL
DERIV_PUBLIC_WS_URL
DERIV_AUTH_WS_BASE_URL
DERIV_REDIRECT_URI
ALLOW_LIVE_TRADING
ENABLE_BROKER_ACCOUNT_SWITCH
BROKER_APP_ID
BROKER_WS_URL
BROKER_OAUTH_CLIENT_ID
BROKER_REDIRECT_URI
```

For live trading, preserve the current production value of `ALLOW_LIVE_TRADING`. Do not enable live execution merely because the worker infrastructure has moved.

### Telegram variables

If Telegram notifications are used by the workers, copy the existing production values:

```
TELEGRAM_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://algobot.dpdns.org/api/notifications/telegram/webhook/
TELEGRAM_BOT_TOKEN=<existing secret>
TELEGRAM_BOT_USERNAME=<existing value>
TELEGRAM_WEBHOOK_SECRET=<existing secret>
TELEGRAM_API_TIMEOUT=10
TELEGRAM_RETRY_MAX_ATTEMPTS=6
```

### Application URL/security variables

Keep the existing production domains:

```
BASE_URL=https://algobot.dpdns.org
ALGO_API_BASE_URL=https://api.algobot.dpdns.org
ALLOWED_HOSTS=algobot.dpdns.org,www.algobot.dpdns.org,api.algobot.dpdns.org
CORS_ALLOWED_ORIGINS=https://algobot.dpdns.org
CSRF_TRUSTED_ORIGINS=https://algobot.dpdns.org
```

The worker processes do not need a public Railway domain.

## Redis decision

Do not assume that a Render internal Redis URL will work from Railway.

The existing Render Key Value service uses private-network URLs for Render-to-Render communication. External access must be explicitly enabled and allowlisted.

For the temporary Railway phase, the cleaner topology is:

```
Render Web/API
       |
       +---- production PostgreSQL
       |
       +---- Railway Redis (public/TCP access, authenticated)
                         |
                         +---- Railway Worker
                         +---- Railway Beat
                         +---- Railway MarketData
                         +---- Railway LiveMarketStream
```

If the current Render Redis is retained instead, Railway must use its authenticated external connection and the Render Key Value IP allowlist must permit the required Railway egress addresses. Do not expose Redis broadly just to make the connection work.

### Recommended temporary approach

Create a Railway Redis service in the same Railway project.

Railway Redis is private by default. If the Render web service must connect to it, enable Railway Redis public networking/TCP access and use its generated public connection variable/URL. Treat that URL as a secret.

Then set:

```
REDIS_URL=<Railway Redis connection URL>
CELERY_BROKER_URL=<same Railway Redis URL>
CELERY_RESULT_BACKEND=<same Railway Redis URL>
```

on both Render Web/API and all Railway worker services.

**Do this only during the controlled migration window**, because changing the broker changes where queued Celery messages live.

## Database decision

For the first Railway phase, keep the existing production PostgreSQL database rather than migrating application data at the same time.

Point the Railway workers at the existing production `DATABASE_URL`.

This reduces migration risk. Oracle can later receive the worker processes without requiring another database migration.

Before switching worker platforms, verify that the PostgreSQL provider permits external connections and that its connection credentials are available.

## Railway service settings

For each worker:

- Source: GitHub
- Repository: `Fazul7506/AlgoBot`
- Branch: `main`
- Build: allow Railway Railpack to detect Python, unless the project later adds a dedicated Dockerfile
- Start command: one of the four commands above
- Restart policy: restart on failure
- Replicas: **1** initially

Keep **Beat at exactly one replica**. Multiple Beat instances would duplicate scheduled tasks.

Keep MarketData at one replica initially because its queue and worker concurrency are deliberately isolated.

Keep LiveMarketStream at one replica initially to avoid duplicate market-stream consumers.

## Deployment order

Deploy in this order:

1. Railway Redis
2. Railway `AlgoBot-Worker`
3. Railway `AlgoBot-Beat`
4. Railway `AlgoBot-MarketData`
5. Railway `AlgoBot-LiveMarketStream`

Then validate each service before touching Render.

## Validation checklist

### General worker

Logs should show a healthy Celery worker connected to Redis and consuming the `celery` queue.

### Beat

Logs should show Beat starting successfully and publishing scheduled tasks.

### MarketData

The deployment must pass:

```
python manage.py check_market_data_worker
```

and then start the `market_data` queue worker.

### LiveMarketStream

Logs should show the management command starting and maintaining its live market connection.

### Application

After workers are healthy:

- confirm the Render web/API remains healthy;
- confirm Celery tasks are being consumed;
- confirm scheduled tasks execute once;
- confirm market-data ingestion is progressing;
- confirm live market data is arriving;
- confirm no duplicate stream consumers exist;
- confirm no task backlog is growing unexpectedly;
- confirm trading remains governed by the existing `ALLOW_LIVE_TRADING` setting.

## Railway trial warning

Railway's current free trial is a bridge, not the permanent hosting plan.

The trial provides a one-time $5 credit for up to 30 days. After the trial, the Free plan provides $1/month of credit, which is not a realistic permanent budget for four always-on production worker services.

Therefore:

**Do not design AlgoBot around Railway Free as its permanent worker platform.**

Use Railway to get the managed worker architecture operational now, while preparing Oracle Always Free as the long-term worker host once the required payment/identity verification is available.

## Oracle handoff architecture

The target long-term architecture is:

```
                    ┌──────────────────────────┐
                    │ Render Web/API            │
                    │ algobot.dpdns.org         │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │ Production PostgreSQL     │
                    └──────────────────────────┘

                                 │
                                 │ Redis
                                 ▼
                    ┌──────────────────────────┐
                    │ Oracle Always Free VM(s)  │
                    │                          │
                    │ Celery Worker             │
                    │ Celery Beat               │
                    │ MarketData Worker         │
                    │ LiveMarketStream          │
                    └──────────────────────────┘
```

The four Railway start scripts are deliberately portable. The same commands can be run on Oracle using systemd, Docker, or another process supervisor without changing AlgoBot application code.

## Oracle migration principle

When Oracle is ready:

1. Provision Oracle Always Free compute.
2. Install Python/system dependencies.
3. Clone `Fazul7506/AlgoBot`.
4. Create the production environment variables securely.
5. Install `requirements/base.txt`.
6. Run the same four worker entrypoints.
7. Validate all four workers.
8. Stop Railway workers.
9. Confirm the Oracle workers are consuming the queues.
10. Keep Render Web/API unchanged unless a separate infrastructure migration is intentionally planned.

Do not migrate Render Web/API, PostgreSQL, Redis, and workers simultaneously. One infrastructure boundary at a time is safer.

## No-secret rule

Never commit:

- `SECRET_KEY`
- `DATABASE_URL`
- Redis passwords/URLs
- Deriv tokens/secrets
- broker OAuth secrets
- Telegram bot tokens
- payment-provider secrets
- Google OAuth secrets
- encryption keys

into GitHub.

Use Railway Variables, Render environment variables, and later Oracle's secret/environment mechanism.

## Current migration status

- [x] Existing four worker roles audited
- [x] Railway-compatible entrypoint scripts added
- [x] Self-hosted GitHub worker workflow removed previously
- [ ] Create Railway project
- [ ] Create Railway Redis
- [ ] Create four Railway worker services
- [ ] Configure production variables
- [ ] Validate all four Railway workers
- [ ] Switch the production Redis connection if required
- [ ] Stop/remove Render worker services only after validation
- [ ] Prepare Oracle Always Free
- [ ] Move the four workers from Railway to Oracle
- [ ] Retire Railway workers

