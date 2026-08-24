# Phase 4 — Base Template Production Shell

Status: COMPLETE AND WORKING

## Scope

`templates/base.html` is now a thin application composition layer rather than a container for page-independent CSS and runtime logic.

## Implemented

- global design system loaded first
- shared shell CSS extracted to `static/css/base_shell.css`
- shared shell behavior extracted to `static/js/base_shell.js`
- API execution timeout/routing guard extracted to `static/js/core/api_execution_guard.js`
- broker state/data/security layers loaded in dependency order
- existing broker UI retained as the integration consumer
- broker state bridge loaded after the broker UI
- inline base shell style block removed
- inline API runtime guard removed
- inline toast/duplicate-account cleanup removed
- skip-link, semantic navigation landmarks and keyboard-visible focus remain part of the shared shell
- responsive mobile navigation and collapsible desktop sidebar behavior provided by the shell layer
- global broker connection indicator reflects canonical broker state

## Dependency order

`design_system.css -> base_shell.css -> page styles`

`broker_state.js -> frontend_data_contract.js -> broker_payload_guard.js -> api_execution_guard.js -> live_broker_ui.js -> broker_state_bridge.js -> base_shell.js -> page scripts`

## Exit gate

- base template remains inherited by downstream pages
- no inline shell CSS remains
- no inline execution guard remains
- no duplicate broker implementation introduced
- broker state is visible globally
- navigation/mobile shell is centralized
- page-specific styles/scripts still have `extra_css` / `extra_js` extension points

Phase 4 is complete and working at the shared-template architecture level. Individual pages are deliberately not marked production-complete until their own page phases pass the full gate.
