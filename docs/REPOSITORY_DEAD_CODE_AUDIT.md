# Repository dead-code and app-retirement audit

**Scope snapshot:** Git tree for `Fazul7506/AlgoBot` default branch `main`, inspected 2026-10-23. The tree contains 1,272 tracked paths (recursive Git tree was not truncated), including 26 application packages under `apps/`. This is a dependency/risk inventory and retirement plan, not a claim that every Python symbol has been proven live or dead. No production code is deleted by this audit because the available inspection does not include executable whole-repository reference analysis or the deployed database/runtime.

## Rules for deciding deletion

A path is deletable only after all applicable checks are green:

1. Python imports, dynamic imports, Django app loading, `AppConfig.ready()`, signal registration, model discovery, admin registration, management commands, and migrations.
2. URL patterns and reverse names, middleware/settings strings, serializers, task names, Celery beat schedules/routes/imports, worker queue configuration, and scheduled/cron/deploy commands.
3. Template inheritance/includes, static asset references from HTML/CSS/JS, URL strings built dynamically, and references in tests/docs/scripts.
4. Data lifecycle: migration dependencies, content types, permissions, database tables, user data, broker credentials, and model artifacts. Code absence is not proof that stored data can be dropped.
5. CI checks, Render Blueprint, Procfile, requirements files, environment-variable templates, release commands, and operational runbooks.
6. Run the relevant tests and Django checks on the candidate branch; inspect migration plan against a production-like database snapshot; deploy canary/staging; verify critical workflows and rollback before removal.

Search-based “no references” is a candidate signal, not sufficient evidence. Do not delete migrations or data tables merely because application code appears unused.

## Confirmed architecture entry points and dependencies

- `deriv_platform/settings.py` selects environment-specific settings from `config.settings.development` / `config.settings.production`.
- `config/settings/base.py` explicitly registers Django applications and middleware by dotted-path strings. An app may have few ordinary imports and still be loaded by Django.
- `deriv_platform/urls.py` wires browser pages and APIs, including predictions, trading, market data, notifications, monitoring, observability, risk, portfolio, automation, and integrations.
- `deriv_platform/celery.py` declares recurring work by task-name strings. Task names in beat schedules can be missed by simple import/reference scans.
- `config/settings/celery.py` declares queue names, explicit task imports, routes, and task annotations; market-data work depends on the isolated `market_data` queue.
- `render.yaml` defines the web service, general worker, beat worker, and additional service configuration. `Procfile` also documents process commands. A code-retirement change must reconcile these sources rather than deleting one based on the other.
- `requirements/base.txt` is used by Render build commands. `requirements.txt` and environment-specific requirements are separate manifests and need dependency ownership analysis before consolidation.
- `manage.py`, Django migration commands, `collectstatic`, ASGI/Daphne, Redis, Celery, database and static-file settings are runtime dependencies.

## Django app inventory and initial decision

All 26 packages below are explicitly present in `INSTALLED_APPS` in `config/settings/base.py`. Therefore none can responsibly be classified as “unregistered/unused app” from a filename scan. Their registration means Django loads them and can discover models, migrations, admin, signals, and app configuration. The correct first decision is **retain pending dependency proof**, not delete.

| App | Initial decision | Main risk to inspect before any retirement |
|---|---|---|
| `apps.ai_engine` | Retain | Prediction/model registry, tasks, migrations, APIs, model artifacts |
| `apps.analysis` | Retain | Analysis endpoints, templates and report dependencies |
| `apps.automation` | Retain | Scheduled task in Celery Beat and workflow state |
| `apps.backtesting` | Retain | Backtest tasks, history and stored results |
| `apps.brokers` | Retain | Broker connections, credentials and integration APIs |
| `apps.copy_trading` | Audit candidate only | App-specific URL/task/model references and stored subscriptions |
| `apps.deployment` | Audit candidate only | Deployment operations, management commands and configuration hooks |
| `apps.developer` | Retain | API middleware, developer routes, access controls |
| `apps.enterprise` | Audit candidate only | Tenant/enterprise permissions, billing and policy integrations |
| `apps.execution` | Retain | Celery Beat execution-queue recovery task and trading safety |
| `apps.feature_store` | Audit candidate only | Feature schema/model training and historical feature data |
| `apps.health` | Retain | Root health-check route and deployment health checks |
| `apps.indicators` | Retain pending scan | Strategy/analysis imports and computed indicator contracts |
| `apps.market_data` | Retain | Broker candles, market catalogue, URLs, tasks, dedicated queue |
| `apps.monitoring` | Retain | Two URL mounts and monitoring tasks |
| `apps.notifications` | Retain | User-facing channels, Telegram Beat tasks and delivery records |
| `apps.observability` | Retain | API routes and observability page |
| `apps.optimization` | Audit candidate only | Strategy tuning, tasks, and saved optimization results |
| `apps.portfolio` | Retain pending scan | Portfolio views, account and position data |
| `apps.risk` | Retain | Risk controls and trading safety dependencies |
| `apps.simulation` | Audit candidate only | Simulation workflows, model evaluation and stored results |
| `apps.smart_money` | Retain pending scan | Page URL configuration, signals and strategy references |
| `apps.strategies` | Retain | Strategies pages, tasks, prediction evidence and trading workflows |
| `apps.tenants` | Retain | Tenant boundaries and data ownership/security |
| `apps.trading` | Retain pending scan | Trading app configuration, execution and URL references |
| `apps.training` | Audit candidate only | Model-training orchestration, registered-model lifecycle and data/artifacts |

“Retain pending scan” and “Audit candidate only” are prioritization labels, **not a finding that the app is unused**. No app should be dropped from `INSTALLED_APPS` until its models, migrations, signals, app configuration and indirect references are traced. The apps that are likely to overlap in domain names (`ai_engine` / `training` / `feature_store`, and `trading` / `execution` / `simulation`) are candidates for architecture-boundary review, not automatic merges.

## File-level candidates and migration decisions

The current remote tree listing establishes file existence, not semantic reachability. As a result, this pass deliberately does not label individual source files “safe to delete” without reference evidence. The following are the required migration decisions for candidates identified by static analysis:

- **Duplicate implementation:** choose one canonical implementation; move callers in a compatibility commit; keep a temporary import/re-export shim only if external or dynamic references exist; remove shim in a later release after telemetry/tests confirm zero use.
- **Unused Django app:** first move its routes/features behind a feature flag or compatibility redirect; migrate or archive owned records; preserve required content types/permissions until data migration is verified; remove from `INSTALLED_APPS` only after model/migration/signal/task consumers are gone; drop tables only in a separately reviewed irreversible migration.
- **Unused Celery task:** remove beat schedules, routes, imports and worker queue references together; inspect queued messages and task names before rollout.
- **Unused template/static asset:** search inheritance, includes, static tags, JS fetch paths, CSS `url()`, and runtime-generated paths; remove only after template and browser tests.
- **Unused dependency:** establish import ownership across production, management commands, tests and optional model paths; remove from every requirements manifest in one coordinated change; rebuild from clean environment and test Render build.
- **Superseded config/deploy file:** select one source of truth only after comparing effective service definitions; retain a compatibility period where deploy tooling consumes both files.
- **Unused migration:** do not delete historical migrations in a live database project. If squashing is justified, follow Django's supported squash process, test fresh install and upgrade from representative existing migration states, then remove replaced migrations only after all deployed environments have advanced beyond them.

## Required automated audit to finish before destructive cleanup

Run in a clean checkout with production dependency extras installed:

1. Enumerate tracked Python modules and use AST/import graph analysis plus `vulture` as a *candidate detector*; corroborate findings with repository-wide text search and dynamic-path inventory.
2. Parse settings and enumerate each installed app's `AppConfig`, models, migration graph, admin, signals, URLs, management commands and tasks.
3. Build a graph of URL routes, template includes/extends, static references, JS API paths, Celery schedule/routes/imports, scripts, Docker/Render/Procfile commands, requirements and env keys.
4. Run `python manage.py check --deploy`, `python manage.py showmigrations`, `python manage.py migrate --plan`, the complete test suite, lint/type checks, and a clean production dependency build. Compare against a sanitized production schema/data snapshot without exposing secrets.
5. Generate a machine-readable candidate manifest with `path`, `symbols`, `reference evidence`, `runtime/dynamic risk`, `data risk`, `migration/compatibility plan`, `owner`, `tests`, and `decision` (keep, consolidate, deprecate, delete).
6. Delete only candidates whose evidence and tests pass; run the suite after each coherent batch. Deploy and verify predictions, market data, order execution, risk checks, billing, authentication, notifications, automation and rollback before merging.

## Completion status

This document is the initial evidence-backed architecture inventory and safe retirement plan. It is **not** a claim that the complete 1,272-path tree has been proven free of unused files. A complete file-by-file dead-code verdict requires executing the graph/test workflow above against a checkout; the GitHub file/tree inspection alone cannot prove dynamic runtime reachability or safely justify destructive changes. The next implementation increment should add the repeatable audit tooling and publish its generated candidate manifest, then handle each verified deletion in reviewable batches.
