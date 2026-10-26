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
  const logBody = root.querySelector('[data-mission-log-body]');
  const logCount = root.querySelector('[data-mission-log-count]');
  const logSearch = root.querySelector('[data-mission-log-search]');
  const logLevel = root.querySelector('[data-mission-log-level]');
  const logWindow = root.querySelector('[data-mission-log-window]');
  const logStream = root.querySelector('[data-mission-log-stream]');
  const logRefresh = root.querySelector('[data-mission-log-refresh]');
  const logPause = root.querySelector('[data-mission-log-pause]');
  const logMore = root.querySelector('[data-mission-log-more]');
  const logStatus = root.querySelector('[data-mission-log-status]');
  let logOffset = 0;
  let logHasMore = false;
  let livePaused = false;
  const renderLogs = (events) => {
    if (!logBody || !Array.isArray(events)) return;
    logBody.replaceChildren();
    events.forEach((event) => {
      const row = document.createElement('tr');
      const time = document.createElement('td');
      const level = document.createElement('td');
      const area = document.createElement('td');
      const message = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = 'monitoring-badge status-' + statusClass(event.level);
      const dot = document.createElement('i');
      badge.append(dot, document.createTextNode(String(event.level || 'INFO')));
      time.textContent = event.timestamp ? new Date(event.timestamp).toLocaleString() : '—';
      level.appendChild(badge);
      area.textContent = String(event.stream || 'application') + ' · ' + String(event.source || 'AlgoBot');
      message.textContent = String(event.message || '');
      const details = event.details || event.error_category || event.resolution || event.operation_id;
      if (details) {
        const disclosure = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = 'View details';
        const detailText = document.createElement('pre');
        detailText.className = 'mission-log-details';
        detailText.textContent = [
          event.category ? 'Category: ' + event.category : '',
          event.status ? 'Status: ' + event.status : '',
          event.operation_id ? 'Operation: ' + event.operation_id : '',
          event.duration_ms !== null && event.duration_ms !== undefined ? 'Duration: ' + event.duration_ms + ' ms' : '',
          event.error_category ? 'Failure type: ' + event.error_category : '',
          event.resolution ? 'Suggested action: ' + event.resolution : '',
          details && typeof details === 'string' ? 'Details: ' + details : (details && typeof details === 'object' ? 'Details: ' + JSON.stringify(details, null, 2) : '')
        ].filter(Boolean).join('\\n');
        disclosure.append(summary, detailText);
        message.appendChild(document.createTextNode(' '));
        message.appendChild(disclosure);
      }
      row.append(time, level, area, message);
      logBody.appendChild(row);
    });
    if (logCount) logCount.textContent = String(events.length);
  };
  let logRequest = null;
  const loadLogs = async (reset = true) => {
    if (!logBody) return;
    if (logRequest) logRequest.abort();
    logRequest = new AbortController();
    if (reset) logOffset = 0;
    const params = new URLSearchParams({limit: '100', offset: String(logOffset)});
    if (logWindow?.value && logWindow.value !== 'all') params.set('since_minutes', logWindow.value);
    if (logSearch?.value.trim()) params.set('search', logSearch.value.trim());
    if (logLevel?.value) params.set('level', logLevel.value);
    if (logStream?.value) params.set('stream', logStream.value);
    if (logStatus) logStatus.textContent = 'Refreshing…';
    if (logRefresh) logRefresh.disabled = true;
    try {
      if (!window.AlgoBotFrontendData || typeof window.AlgoBotFrontendData.request !== 'function') {
        throw new Error('Activity feed client is unavailable');
      }
      const response = await window.AlgoBotFrontendData.request('/api/monitoring/mission-events/?' + params.toString(), {signal: logRequest.signal}, 10000);
      const payload = response?.data && typeof response.data === 'object' ? response.data : response;
      const events = Array.isArray(payload) ? payload : payload?.results;
      if (!Array.isArray(events)) throw new Error('Activity feed returned an unexpected response');
      logHasMore = Boolean(payload?.has_more);
      if (payload && !Array.isArray(payload)) logOffset = Number(payload.next_offset || logOffset);
      renderLogs(events);
      if (logMore) logMore.disabled = !logHasMore;
      if (logStatus) logStatus.textContent = 'Updated ' + new Date().toLocaleTimeString() + (livePaused ? ' · live updates paused' : '');
      root.removeAttribute('data-log-error');
    } catch (error) {
      if (error?.name !== 'AbortError') {
        root.setAttribute('data-log-error', 'true');
        if (logStatus) logStatus.textContent = 'Refresh failed — showing last available events';
      }
    } finally {
      if (logRefresh) logRefresh.disabled = false;
    }
  };
  refresh?.addEventListener('click', load);
  logRefresh?.addEventListener('click', () => loadLogs(true));
  logPause?.addEventListener('click', () => {
    livePaused = !livePaused;
    logPause.textContent = livePaused ? 'Resume live updates' : 'Pause live updates';
    logPause.setAttribute('aria-pressed', String(livePaused));
    if (logStatus) logStatus.textContent = livePaused ? 'Live updates paused' : 'Live updates resumed';
    if (!livePaused) loadLogs(false);
  });
  logMore?.addEventListener('click', () => { if (logHasMore) loadLogs(false); });
  [logSearch, logLevel, logStream, logWindow].forEach((control) => {
    control?.addEventListener(control === logSearch ? 'input' : 'change', () => {
      if (control !== logSearch || control.value.length === 0 || control.value.length >= 2) loadLogs(true);
    });
  });
  if (logBody) {
    loadLogs(true);
    window.setInterval(() => { if (!livePaused) loadLogs(false); }, 5000);
  }
})();
