/* Cancellation errors are expected control flow and must not become global outage toasts. */
(() => {
  'use strict';
  if (window.__algoBotAbortErrorGuard) return;
  window.__algoBotAbortErrorGuard = true;
  window.addEventListener('algobot:api-error', event => {
    const detail = event.detail || {};
    const code = String(detail.code || '').toUpperCase();
    const message = String(detail.message || '');
    if (code === 'REQUEST_ABORTED' || /(?:signal|request) is aborted|abort(?:ed|error)/i.test(message)) event.stopImmediatePropagation();
  }, true);
})();
