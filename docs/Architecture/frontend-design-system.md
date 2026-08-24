# AlgoBot Frontend Design System

Status: PHASE 3 COMPLETE AND WORKING

## Purpose

Provide one shared visual and interaction vocabulary for every template/page migration. New pages use these primitives instead of introducing one-off button, form, status, card or state styles.

## Core tokens

- spacing: 4/8/12/16/20/24/32/40px
- radii: 8/12/16/22px
- semantic surfaces, borders, text and muted text
- semantic states: success, warning, info, danger, degraded/unknown
- consistent focus ring

## Shared primitives

- `.ds-card`
- `.ds-btn`, `.ds-btn--primary`, `.ds-btn--danger`, `.ds-btn--ghost`
- `.ds-status--connected`, `--ready`, `--connecting`, `--syncing`, `--reconnecting`, `--disconnected`, `--error`, `--degraded`, `--unknown`
- `.ds-field`, `.ds-field__help`, `.ds-field__error`
- `.ds-state`, `.ds-state--error`, `.ds-state--success`
- `.ds-skeleton`

## Accessibility rules

- keyboard focus is always visible
- disabled controls communicate non-interactivity
- loading state can be represented with `aria-busy`
- reduced-motion users receive reduced animation
- controls retain readable inherited typography

## Broker-specific visual rule

Connection status is semantic, not decorative. A page must use the broker state contract to distinguish connected, syncing, reconnecting, disconnected, degraded and unknown states. A green visual state cannot be shown merely because a template rendered successfully.

## Responsive rule

Controls become touch-friendly at mobile widths and cards retain readable padding. Individual page migrations remain responsible for their own responsive information architecture.

## Migration rule

Phase 3 establishes the primitives globally. Phase 4 and every subsequent page phase must replace page-specific patterns with these primitives where practical. Phase 3 does not claim that every existing page has already been visually migrated.
