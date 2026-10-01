# External AlgoBot Workers (zero-cost development option)

Render's Free compute does not include Background Worker services. This directory-free launcher keeps the existing AlgoBot worker architecture intact while allowing the processes to run on a machine you control.

## Processes started

1. General Celery worker: queue `celery`
2. Exactly one Celery Beat scheduler
3. `run_market_stream`
4. Market-data Celery worker: queue `market_data`

These are the same commands represented by `render.yaml`; this is not a replacement worker architecture.

## Connect to the existing Render application

The worker host needs the application's **external** PostgreSQL and Redis/Key Value connection URLs plus the same Django `SECRET_KEY`. Do not copy secrets into GitHub or commit them.

Set:

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `USE_REDIS=true`
- `USE_CELERY=true`
- `DJANGO_ENV=production`
- `DJANGO_SETTINGS_MODULE=deriv_platform.settings`

The launcher derives `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` from `REDIS_URL` when they are not explicitly set.

## Run locally

Create a virtual environment, install `requirements/base.txt`, copy `.env.external-workers.example` to a local environment file, populate the values from Render, load that environment, then run:

```bash
python scripts/run_external_workers.py
```

Keep the machine online while the workers are required. If it is shut down, these workers are unavailable; AlgoBot must not represent them as healthy.

## Production warning

This is a zero-cost learning/development arrangement, not a 24/7 production hosting guarantee. Do not use a personal machine for unattended real-money trading. For real-money production, move these same processes to persistent worker infrastructure and verify queue, broker, market-data, and execution health before enabling execution.
