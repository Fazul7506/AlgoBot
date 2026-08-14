# AlgoBot Phase 20 — Production Deployment

## Status

Phase 19 is the known-good baseline: 38 tests passed.

Phase 20 starts with production configuration hardening. No live credentials are included.

## Local preflight

From `deriv_platform`:

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py seed_markets
python manage.py test
```

## Production configuration

1. Copy `.env.production.example` to `.env.production`.
2. Replace every `REPLACE_*` value.
3. Set `BASE_URL`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS` to the real HTTPS domain.
4. Generate a strong `SECRET_KEY`.
5. Configure PostgreSQL, Redis, Deriv OAuth, email, payment and observability credentials.
6. Never commit `.env.production`.

## Docker deployment

```powershell
docker compose --env-file .env.production -f docker-compose.production.yml build
docker compose --env-file .env.production -f docker-compose.production.yml up -d
docker compose --env-file .env.production -f docker-compose.production.yml logs -f web
```

The web container runs migrations and `collectstatic` before Gunicorn starts.

## Required external layer

Place HTTPS termination/reverse proxy in front of the web container. The production settings trust `X-Forwarded-Proto=https`.

## Health checks

- `/health/live/` — process liveness
- `/health/ready/` — database and cache readiness
- `/health/` — readiness alias

A successful readiness response requires both database and cache checks.

## Important

Do not use the development SQLite database, development secret, console email backend, or HTTP callback URL in production.

Do not claim the system is live until HTTPS, DNS, PostgreSQL, Redis, Deriv OAuth redirect configuration, email, backups, and monitoring have all been verified.
