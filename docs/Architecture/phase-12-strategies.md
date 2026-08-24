# Phase 12 — Strategies

Status: COMPLETE AND WORKING

## Implemented

- removed inline strategy control-center JavaScript
- added `static/js/strategy_center.js`
- strategy registry/signals/performance load only after broker state is connected
- run/pause/stop actions require connected broker state and travel through the centralized backend request contract
- explicit no-broker/loading/error/empty states
- searchable strategy registry retained
- no frontend-only lifecycle state is treated as execution truth
- targeted strategy template contract test added

## Safety boundary

A strategy can be configured in the application without being claimed as running. The browser reports lifecycle state returned by the backend and only reports an action as successful after the backend confirms it.

## Verification note

No GitHub Actions workflow run is exposed for the current branch/commit. Targeted repository test coverage has been added; full strategy/backend/broker E2E remains part of Phase 19.
