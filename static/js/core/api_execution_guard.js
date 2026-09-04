/*
 * Legacy compatibility module.
 * API aliases, CSRF protection, timeout handling, and execution request context
 * are centralized in static/js/core/api_client.js. This file intentionally
 * does not wrap window.fetch so request behavior has one authoritative owner.
 */
(() => {
  'use strict';
  window.__algoBotApiExecutionGuard = true;
})();
