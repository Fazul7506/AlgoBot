# AlgoBot — Current Canonical Reference

**Status:** Active source-of-truth reference
**Updated:** 2026-09-04

This document replaces the older audit/session references for day-to-day implementation decisions. Historical documents may remain in Git history, but runtime code must follow the canonical replacements below.

## 1. API routing

| Retired reference | Canonical replacement | Rule |
|---|---|---|
| `/api/v1/...` | `/api/...` | Use the single canonical API namespace. |
| `/data/...` | `/api/...` | Data is served through the canonical API; do not add a second API namespace. |
| `API_V1_INCLUDES` | direct `/api/` includes | No version-specific duplicate URL assembly. |
| `v1_*` route names | canonical route names | Do not create new version-specific route names. |

The legacy `/api/v1/` and `/data/` aliases have been removed from `deriv_platform/urls.py`.

## 2. AI/ML

| Retired reference | Canonical replacement | Rule |
|---|---|---|
| `apps/ml_models/` hardcoded model wrappers | `apps/ai_engine/` training/services + `apps/trading/ai/ensemble.py` | Production AI must use the real training/inference pipeline. |
| `BaseAlgoBotModel` placeholder predictions | configured model inference | Never use hardcoded UP/55% style predictions. |
| `apps.ml_models` in `INSTALLED_APPS` | removed | The retired scaffold is no longer part of runtime Django configuration. |

## 3. Execution semantics

| Retired/incorrect pattern | Canonical replacement | Rule |
|---|---|---|
| Manual order → `ExecutionQueueService.enqueue()` | `ExecutionEngine.place_manual_order()` | Manual BUY/SELL is directly user-driven and must not enter the strategy queue. |
| Manual click waiting for strategy signal | direct manual request | A manual action executes only because the user explicitly requested it. |
| Strategy order treated as manual | `ExecutionEngine.place_order()` + queue | Strategy execution remains autonomous and queued. |
| Browser retry after broker-unknown | reconciliation state | Never silently duplicate an order after an uncertain broker result. |

## 4. API security / CSRF

| Retired reference | Canonical replacement | Rule |
|---|---|---|
| `/api/csrf/` bootstrap endpoint | no API CSRF bootstrap | API/data requests are exempted from Django CSRF processing by the API-aware middleware. |
| Browser JS CSRF retry/bootstrap logic | authenticated API client contract | Do not reintroduce API CSRF token fetching. |
| Normal HTML form CSRF removal | Django standard CSRF for HTML | API CSRF removal does not mean HTML form protection is disabled. |

## 5. Shared module pages

| Retired/broken reference | Canonical replacement |
|---|---|
| Missing `components/enterprise_page.html` | `templates/components/enterprise_page.html` |
| `data-page-id` only | canonical `data-page` plus `data-page-id` compatibility marker |
| Missing `.enterprise-page-body` mount point | shared `enterprise-page-body` workspace container |

The shared page shell is now aligned with the AI predictions workspace contract.

## 6. Production validation rules

1. Canonical URLs must resolve through the current route configuration.
2. New frontend code must call `/api/...`, not `/api/v1/...` or `/data/...`.
3. Manual execution must remain explicitly user initiated.
4. Strategy execution may remain autonomous and queued.
5. Broker-unknown execution results must reconcile rather than auto-submit again.
6. AI output is advisory and remains subject to risk and execution gates.
7. No retired scaffold may be re-added merely to satisfy an old import or test; update the caller to the canonical implementation instead.

## 7. Current implementation sources

- Trading execution: `apps/execution/engine.py`
- Risk: `apps/risk/`
- Market data: `apps/market_data/`
- AI: `apps/ai_engine/` and `apps/trading/ai/ensemble.py`
- Strategies: `apps/strategies/`
- Canonical API routing: `deriv_platform/urls.py`
- Shared module shell: `templates/components/enterprise_page.html`
- Predictions workspace: `static/js/predictions_workspace_fix.js`
