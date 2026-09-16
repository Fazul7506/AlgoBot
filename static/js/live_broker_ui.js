/* Legacy compatibility entry point.
 * Broker account state, selection and switching are owned by the canonical
 * core/account_context.js + core/broker_state.js modules.
 * This file intentionally has no network/account-selection side effects.
 */
(() => {
  'use strict';
  if (window.__algoBotLegacyLiveBrokerUI) return;
  window.__algoBotLegacyLiveBrokerUI = true;
})();
