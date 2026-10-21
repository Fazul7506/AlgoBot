(() => {
  const root = document.querySelector('[data-monitoring-dashboard]');
  if (!root) return;
  const refresh = root.querySelector('[data-monitoring-refresh]');
  const updated = root.querySelector('[data-monitoring-updated]');
  const setText = (selector, value) => {
    if (value === undefined || value === null) return;
    root.querySelectorAll(selector).forEach((el) => { el.textContent = String(value); });
  };
  const statusClass = (value) => String(value || 'unknown').toLowerCase().replace(/[^a-z0-9_-]/g, '-');
  const setStatus = (selector, value) => {
    if (value === undefined || value === null) return;
    root.querySelectorAll(selector).forEach((el) => {
      el.textContent = String(value).replaceAll('_', ' ');
      el.dataset.status = statusClass(value);
    });
  };
  const load = async () => {
    if (refresh) {
      refresh.disabled = true;
      refresh.setAttribute('aria-busy', 'true');
      refresh.title = 'Refreshing monitoring data';
    }
    try {
      if (!window.AlgoBotFrontendData || typeof window.AlgoBotFrontendData.request !== 'function') {
        throw new Error('Monitoring refresh is unavailable');
      }
      const response = await window.AlgoBotFrontendData.request('/api/monitoring/dashboard/', {}, 10000);
      const data = response?.data && typeof response.data === 'object' ? response.data : response;
      setStatus('[data-system-status-text]', data.overall_system_health);
      setStatus('[data-broker-status-text]', data.broker_status);
      setText('[data-current-trades]', data.current_trades);
      setText('[data-active-alerts]', data.active_alerts);
      setText('[data-open-incidents]', data.open_incidents);
      setText('[data-current-predictions]', data.current_predictions);
      if (updated) {
        updated.textContent = new Date().toLocaleTimeString();
        updated.removeAttribute('title');
      }
      root.removeAttribute('data-refresh-error');
    } catch (error) {
      root.setAttribute('data-refresh-error', 'true');
      if (updated) {
        updated.textContent = 'Refresh unavailable';
        updated.title = String(error?.message || 'Could not refresh monitoring data');
      }
    } finally {
      if (refresh) {
        refresh.disabled = false;
        refresh.removeAttribute('aria-busy');
        refresh.title = 'Refresh monitoring data';
      }
    }
  };
  refresh?.addEventListener('click', load);
})();
