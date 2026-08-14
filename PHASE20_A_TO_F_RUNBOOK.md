# AlgoBot Phase 20A–20F Production Runbook

## Current baseline

Phase 19/20 local baseline is clean:
- `manage.py check` — 0 issues
- `makemigrations --check` — no changes
- migrations — applied
- `seed_markets` — 8 active markets
- tests — 38 passed

## 20A — Production configuration
Implemented in this build:
- production settings selector via `DJANGO_ENV=production`
- `DEBUG=False`
- required host/origin validation
- production secret validation
- secure cookies
- HTTPS redirect
- HSTS
- PostgreSQL/Redis enforcement
- optional Sentry
- production environment template

Still requires real deployment values.

## 20B — Production services
Artifacts included:
- Dockerfile
- `docker-compose.production.yml`
- Gunicorn
- PostgreSQL
- Redis
- optional Celery worker
- systemd examples
- Nginx reverse-proxy example

Still requires actual server/container infrastructure.

## 20C — HTTPS / domain
Before go-live:
1. Point DNS at the production ingress.
2. Install/enable a trusted TLS certificate.
3. Set `BASE_URL=https://...`.
4. Set `ALLOWED_HOSTS`.
5. Set `CSRF_TRUSTED_ORIGINS`.
6. Configure Deriv OAuth redirect URI to the exact HTTPS callback.
7. Verify HTTP redirects to HTTPS.
8. Verify `/health/live/` and `/health/ready/`.

## 20D — Deployment
Recommended order:
1. Provision PostgreSQL.
2. Provision Redis.
3. Create production `.env.production` outside source control.
4. Build the application.
5. Run `python manage.py check --deploy`.
6. Run `python manage.py migrate --noinput`.
7. Run `python manage.py collectstatic --noinput`.
8. Seed/verify markets.
9. Start Gunicorn.
10. Start workers if Celery is enabled.
11. Put Nginx/load balancer in front.
12. Verify logs and health.

## 20E — Production validation
Run all of:
- Django deploy checks
- migration check
- health liveness/readiness
- database connectivity
- Redis connectivity
- static assets
- login/auth flow
- Deriv OAuth callback
- market streaming
- API authentication
- developer API key lifecycle
- webhooks
- billing test mode
- notifications
- risk controls
- paper trading
- copy trading
- monitoring/observability
- backup + restore test
- worker restart/recovery
- rate limiting
- HTTPS/security headers

## 20F — Go-live gate
Do not declare LIVE until every required production integration is verified.

Required:
- real HTTPS domain
- PostgreSQL backup/restore
- Redis persistence/recovery strategy
- real Deriv OAuth credentials
- real callback URL
- email provider
- payment provider/webhooks if enabled
- monitoring/alerting
- secrets stored outside Git
- least-privilege service accounts
- tested rollback
- successful smoke test

## Rollback
Keep the known-good Phase 19 archive untouched. For a failed deployment:
1. stop the new release
2. restore the previous application release
3. restore the database only if a migration requires it
4. restart workers/web
5. verify `/health/ready/`
6. inspect logs before retrying

Never use destructive database commands as a first response to a failed deployment.
