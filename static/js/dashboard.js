/* Legacy compatibility entry point.
 * The production dashboard is owned by dashboard_command_center.js.
 * Keep this file side-effect free so old cached references cannot create a
 * second account/data controller or resurrect removed account preference state.
 */
(() => {
  'use strict';
  if (window.__algoBotLegacyDashboard) return;
  window.__algoBotLegacyDashboard = true;
})();
