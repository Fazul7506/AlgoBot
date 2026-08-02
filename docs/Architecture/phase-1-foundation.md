# AlgoBot v1.0 Enterprise — Phase 1 Foundation

This foundation introduces a commercial-grade project shell while preserving the current runnable Django apps.

## Key decisions

- Keep the existing `core` and `trading` Django apps in place until each domain can be extracted safely.
- Add the target `apps/` domain map as placeholders for future bounded-context migrations.
- Split settings into `config/settings/` modules for base, database, cache, email, broker, security, logging, Celery, development, production, and testing.
- Route secrets and provider credentials through environment variables documented in `.env.example`.
- Establish shared top-level `services/`, `api/v1/`, `urls/`, `templates/`, `static/`, `logs/`, `requirements/`, and `tests/` foundations.

## Migration strategy

1. Stabilize settings and environment loading.
2. Add tests around existing behavior before moving code.
3. Move one bounded context at a time from `core` or `trading` into the matching future app.
4. Keep backwards-compatible imports during each migration window.
5. Remove compatibility shims only after tests and URLs prove the new app owns the behavior.
