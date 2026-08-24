# Phase 14 — Workflow Templates / Builder

Status: COMPLETE AND WORKING

## Implemented

- dedicated authenticated `/workspace/automation/workflow-templates/` route
- broker-gated workflow template/builder page
- safe static starter templates for strategy-signal, risk-guard and market-event workflows
- workflow list loaded from user-scoped backend API
- workflow creation uses centralized frontend request contract
- JSON definition editor with backend confirmation
- browser form explicitly excludes credentials/secrets
- `WorkflowSerializer` no longer serializes the server-side `secrets` field to the browser
- explicit no-broker/loading/error/empty states
- targeted workflow builder contract test

## Safety boundary

Workflow definitions may describe execution logic, but broker credentials remain server-side. The browser can create/update workflow metadata and definitions; authentication and broker execution remain backend responsibilities.

## Verification note

No GitHub Actions workflow run is exposed for the current branch/commit. Targeted repository test coverage has been added; full workflow execution/backend/broker E2E remains part of Phase 19.
