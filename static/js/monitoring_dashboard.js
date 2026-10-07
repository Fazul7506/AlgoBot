(() => {
  const root = document.querySelector('[data-monitoring-dashboard]');
  if (!root) return;
  const refresh = root.querySelector('[data-monitoring-refresh]');
  const updated = root.querySelector('[data-monitoring-updated]');
  const setText = (selector, value) => { const el = root.querySelector(selector); if (el && value !== undefined && value !== null) el.textContent = value; };
  const load = async () => {
    if (refresh) { refresh.disabled = true; refresh.textContent = 'Refreshing…'; }
    try {
      const response = await window.AlgoBotFrontendData.request('/api/monitoring/dashboard/', {}, 10000);
      const data = response;
      setText('[data-system-status]', data.overall_system_health ?? 'Unknown');
      setText('[data-broker-status]', data.broker_status ?? 'Unknown');
      setText('[data-current-trades]', data.current_trades ?? 0);
      setText('[data-active-alerts]', data.active_alerts ?? 0);
      setText('[data-open-incidents]', data.open_incidents ?? 0);
      setText('[data-current-predictions]', data.current_predictions ?? 0);
      if (updated) updated.textContent = new Date().toLocaleTimeString();
    } catch (error) {
      if (updated) updated.textContent = `refresh failed (${error.message})`;
    } finally {
      if (refresh) { refresh.disabled = false; refresh.textContent = 'Refresh telemetry'; }
    }
  };
  refresh?.addEventListener('click', load);
})();
