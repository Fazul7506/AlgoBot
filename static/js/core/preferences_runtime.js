(() => {
  'use strict';
  if (window.AlgoBotPreferences) return;
  const allowed = new Set(['15s', '30s', '1m', '5m', '15m']);
  const durations = { '15s': 15000, '30s': 30000, '60s': 60000, '1m': 60000, '5m': 300000, '15m': 900000 };
  const read = () => {
    const html = document.documentElement;
    const auto = html.dataset.autoRefresh || 'realtime';
    if (durations[auto]) return auto;
    const value = html.dataset.refreshFrequency || '1m';
    return allowed.has(value) ? value : '1m';
  };
  const api = {
    refreshFrequency: read,
    intervalMs(fallback = 30000) {
      const value = read();
      return durations[value] || fallback;
    },
    autoRefreshEnabled() {
      return document.documentElement.dataset.autoRefresh !== 'manual';
    },
  };
  window.AlgoBotPreferences = Object.freeze(api);
  document.addEventListener('algobot:preferences-loaded', event => {
    const prefs = event.detail || {};
    if (allowed.has(prefs.refresh_frequency)) document.documentElement.dataset.refreshFrequency = prefs.refresh_frequency;
    if (typeof prefs.auto_refresh_interval === 'string') document.documentElement.dataset.autoRefresh = prefs.auto_refresh_interval;
  });
})();
