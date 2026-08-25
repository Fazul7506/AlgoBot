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
3. Set `DJANGO_ENV=production`, `BASE_URL`, `ALLOWED_HOSTS`, and
   `CSRF_TRUSTED_ORIGINS` to the real HTTPS domain. The checked-in Procfile
   also sets `DJANGO_ENV=production`; set it explicitly in Render when using a
   dashboard Start Command instead of the Procfile.
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

### Render custom-domain redirect loop

Render terminates public HTTPS, while AlgoBot deliberately leaves
`SECURE_SSL_REDIRECT` disabled in production. Do **not** add a second
application-level HTTP-to-HTTPS redirect in Render's Start Command or
environment variables.

Choose exactly one canonical hostname in Render. If
`www.algobot.dpdns.org` is the public hostname, attach that hostname to the
Render service and point its DNS record directly at the Render target. Do not
configure the DNS provider to forward it to `algobot.dpdns.org`, and do not
configure Render to redirect it back to `www.algobot.dpdns.org`. If both names
are used, only one direction may redirect; remove the reverse redirect before
testing in a private browser window.

## Health checks

- `/health/live/` — process liveness
- `/health/ready/` — database and cache readiness
- `/health/` — readiness alias

A successful readiness response requires both database and cache checks.

## Important

Do not use the development SQLite database, development secret, console email backend, or HTTP callback URL in production.

Do not claim the system is live until HTTPS, DNS, PostgreSQL, Redis, Deriv OAuth redirect configuration, email, backups, and monitoring have all been verified.
