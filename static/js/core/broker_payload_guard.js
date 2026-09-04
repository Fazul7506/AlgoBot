/*
 * Legacy compatibility module.
 *
 * Response normalization and request handling now belong to the authoritative
 * API client. This file intentionally does not wrap window.fetch so legacy
 * script loading cannot create a second request pipeline.
 */
(() => {
  'use strict';
  window.__algoBotBrokerPayloadGuard = true;
})();
