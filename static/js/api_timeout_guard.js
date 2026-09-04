/*
 * Legacy compatibility module.
 * Request timeout, abort handling, CSRF protection, and API error normalization
 * are owned by static/js/core/api_client.js. Keeping this file as a no-op
 * prevents multiple fetch wrappers from competing over request semantics.
 */
(() => {
  'use strict';
  window.__algoBotFetchGuard = true;
})();
