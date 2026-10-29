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
  const logSource = root.querySelector('[data-mission-log-source]');
  const logOperation = root.querySelector('[data-mission-log-operation]');
  const logLevel = root.querySelector('[data-mission-log-level]');
  const logWindow = root.querySelector('[data-mission-log-window]');
  const logStream = root.querySelector('[data-mission-log-stream]');
  const logCategory = root.querySelector('[data-mission-log-category]');
  const logStatusFilter = root.querySelector('[data-mission-log-status-filter]');
  const logRefresh = root.querySelector('[data-mission-log-refresh]');
  const logPause = root.querySelector('[data-mission-log-pause]');
  const logMore = root.querySelector('[data-mission-log-more]');
  const logStatus = root.querySelector('[data-mission-log-status]');
  let logOffset = 0;
  let logHasMore = false;
  let livePaused = false;
  let viewingOlder = false;
  let logSequence = 0;
  let searchDebounce = null;
  const renderLogs = (events, append = false) => {
    if (!logBody || !Array.isArray(events)) return;
    if (!append) logBody.replaceChildren();
    events.forEach((event) => {
      const eventId = String(event.id || '');
      if (append && eventId && Array.from(logBody.children).some((existing) => existing.dataset.eventId === eventId)) return;
      const row = document.createElement('tr');
      if (eventId) row.dataset.eventId = eventId;
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
      const copyMessage = document.createElement('button');
      copyMessage.type = 'button';
      copyMessage.className = 'mission-log-copy';
      copyMessage.textContent = 'Copy message';
      copyMessage.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(String(event.message || ''));
          copyMessage.textContent = 'Copied';
        } catch (_) {
          copyMessage.textContent = 'Copy unavailable';
          copyMessage.title = 'Clipboard access is unavailable in this browser context';
        }
      });
      message.appendChild(copyMessage);
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
        const copyDetails = document.createElement('button');
        copyDetails.type = 'button';
        copyDetails.className = 'mission-log-copy';
        copyDetails.textContent = 'Copy details';
        copyDetails.addEventListener('click', async () => {
          try {
            await navigator.clipboard.writeText(detailText.textContent);
            copyDetails.textContent = 'Copied';
          } catch (_) {
            copyDetails.textContent = 'Copy unavailable';
            copyDetails.title = 'Clipboard access is unavailable in this browser context';
          }
        });
        disclosure.append(summary, copyDetails, detailText);
        message.appendChild(document.createTextNode(' '));
        message.appendChild(disclosure);
      }
      row.append(time, level, area, message);
      logBody.appendChild(row);
    });
    if (logCount) logCount.textContent = String(logBody.children.length);
  };
  let logRequest = null;
  const loadLogs = async (reset = true) => {
    if (!logBody) return;
    if (logRequest) logRequest.abort();
    logRequest = new AbortController();
    const sequence = ++logSequence;
    if (reset) { logOffset = 0; viewingOlder = false; }
    const params = new URLSearchParams({limit: '100', offset: String(logOffset)});
    if (logWindow?.value && logWindow.value !== 'all') params.set('since_minutes', logWindow.value);
    if (logSearch?.value.trim()) params.set('search', logSearch.value.trim());
    if (logSource?.value.trim()) params.set('source', logSource.value.trim());
    if (logOperation?.value.trim()) params.set('operation_id', logOperation.value.trim());
    if (logLevel?.value) params.set('level', logLevel.value);
    if (logStream?.value) params.set('stream', logStream.value);
    if (logCategory?.value) params.set('category', logCategory.value);
    if (logStatusFilter?.value) params.set('status', logStatusFilter.value);
    if (logStatus) logStatus.textContent = 'Refreshing…';
    if (logRefresh) logRefresh.disabled = true;
    try {
      if (!window.AlgoBotFrontendData || typeof window.AlgoBotFrontendData.request !== 'function') {
        throw new Error('Activity feed client is unavailable');
      }
      const response = await window.AlgoBotFrontendData.request('/api/monitoring/mission-events/?' + params.toString(), {signal: logRequest.signal}, 10000);
      if (sequence !== logSequence) return;
      const payload = response?.data && typeof response.data === 'object' ? response.data : response;
      const events = Array.isArray(payload) ? payload : payload?.results;
      if (!Array.isArray(events)) throw new Error('Activity feed returned an unexpected response');
      logHasMore = Boolean(payload?.has_more);
      if (payload && !Array.isArray(payload)) logOffset = Number(payload.next_offset || logOffset);
      renderLogs(events, !reset);
      if (logMore) logMore.disabled = !logHasMore;
      if (logStatus) logStatus.textContent = (viewingOlder ? 'Viewing older events · live refresh paused' : 'Updated ' + new Date().toLocaleTimeString()) + (livePaused ? ' · live updates paused' : '');
      root.removeAttribute('data-log-error');
    } catch (error) {
      if (sequence !== logSequence) return;
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
    if (!livePaused) { viewingOlder = false; loadLogs(true); }
  });
  logMore?.addEventListener('click', () => {
    if (!logHasMore) return;
    viewingOlder = true;
    loadLogs(false);
  });
  const scheduleFilteredSearch = () => {
    window.clearTimeout(searchDebounce);
    searchDebounce = window.setTimeout(() => { viewingOlder = false; loadLogs(true); }, 300);
  };
  [logSearch, logSource, logOperation].forEach((control) => control?.addEventListener('input', scheduleFilteredSearch));
  [logLevel, logStream, logCategory, logStatusFilter, logWindow].forEach((control) => control?.addEventListener('change', () => { viewingOlder = false; loadLogs(true); }));
  let liveTimer = null;
  if (logBody) {
    loadLogs(true);
    const scheduleLiveRefresh = () => {
      if (liveTimer !== null) window.clearInterval(liveTimer);
      if (window.AlgoBotPreferences?.autoRefreshEnabled?.() === false) return;
      liveTimer = window.setInterval(() => {
        if (!livePaused && !viewingOlder && document.visibilityState === 'visible') loadLogs(true);
      }, window.AlgoBotPreferences?.intervalMs?.(15000) || 15000);
    };
    scheduleLiveRefresh();
    document.addEventListener('algobot:preferences-loaded', scheduleLiveRefresh);
    window.addEventListener('algobot:preferences-updated', scheduleLiveRefresh);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && !livePaused && !viewingOlder) loadLogs(true);
    });
    window.addEventListener('pagehide', () => {
      if (liveTimer !== null) window.clearInterval(liveTimer);
      window.clearTimeout(searchDebounce);
      if (logRequest) logRequest.abort();
    }, {once: true});
  }
})();
