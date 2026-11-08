(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const api = (url, options = {}) => window.AlgoBotFrontendData.request(url, options, 10000);
  const set = (key, value, className = '') => {
    const element = $(`[data-status="${key}"]`);
    if (!element) return;
    element.textContent = value;
    element.className = className;
  };
  const operationCount = document => Object.values(document?.paths || {}).reduce(
    (total, path) => total + Object.keys(path || {}).filter(method =>
      ['get', 'post', 'put', 'patch', 'delete', 'options', 'head'].includes(method)
    ).length, 0
  );
  const isRealtimeDocumented = document =>
    Object.keys(document?.paths || {}).some(path => /websocket|realtime|stream|subscribe/i.test(path)) ||
    Object.keys(document?.['x-algobot']?.websocket || {}).length > 0;

  function renderRows(rows) {
    const list = $('[data-status-list]');
    if (!list) return;
    list.replaceChildren(...rows.map(([label, value, status]) => {
      const row = document.createElement('div');
      row.className = 'status-row';
      const name = document.createElement('span');
      name.textContent = label;
      const result = document.createElement('strong');
      result.className = status;
      result.textContent = value;
      row.append(name, result);
      return row;
    }));
  }

  async function load() {
    const refresh = $('[data-status-refresh]');
    if (refresh) { refresh.disabled = true; refresh.textContent = 'Checking…'; }
    const [liveness, readiness, contract] = await Promise.allSettled([
      api('/health/'),
      api('/health/ready/'),
      api('/api/developer/docs/')
    ]);
    const rows = [];
    let document = null;

    if (liveness.status === 'fulfilled' && liveness.value?.status === 'ok') {
      set('gateway', 'Online', 'status-ok');
      rows.push(['API process', 'Online · liveness probe passed', 'status-ok']);
      const commit = liveness.value.commit;
      if (commit) rows.push(['Deployed revision', commit.slice(0, 12), 'status-ok']);
    } else {
      set('gateway', 'Unavailable', 'status-bad');
      rows.push(['API process', 'Unavailable · liveness probe failed', 'status-bad']);
    }

    if (readiness.status === 'fulfilled') {
      const checks = readiness.value?.checks || {};
      const ready = readiness.value?.status === 'ready';
      rows.push(['Application readiness', ready ? 'Ready' : 'Degraded', ready ? 'status-ok' : 'status-warn']);
      for (const [name, value] of Object.entries(checks)) {
        rows.push([name.charAt(0).toUpperCase() + name.slice(1), value ? 'Available' : 'Unavailable', value ? 'status-ok' : 'status-bad']);
      }
    } else {
      rows.push(['Application readiness', 'Could not verify', 'status-warn']);
    }

    if (contract.status === 'fulfilled') {
      const payload = contract.value;
      document = payload?.openapi ? payload : (payload?.payload?.openapi ? payload.payload : payload);
      const count = operationCount(document);
      const version = document?.info?.version || 'unknown';
      set('contract', count ? `Published · ${count} operations` : 'No operations published', count ? 'status-ok' : 'status-bad');
      const versionElement = $('[data-contract-version]');
      if (versionElement) versionElement.textContent = `OpenAPI ${document?.openapi || 'unknown'} · API ${version} · ${count} operations`;
      rows.push(['API contract', count ? `Published · ${count} operations` : 'Empty contract', count ? 'status-ok' : 'status-bad']);
      const auth = document?.authentication?.type || (document?.security?.length ? 'Protected' : 'Not declared');
      rows.push(['Authentication contract', auth, auth === 'Not declared' ? 'status-warn' : 'status-ok']);
      const realtime = isRealtimeDocumented(document);
      set('realtime', realtime ? 'Documented' : 'Not documented', realtime ? 'status-ok' : 'status-warn');
      rows.push(['Realtime API', realtime ? 'Documented in contract · connection not probed' : 'Not documented', realtime ? 'status-warn' : 'status-warn']);
      const trading = Object.keys(document?.paths || {}).some(path => /trade|order|execution/i.test(path));
      set('execution', trading ? 'Routes documented · not live-tested' : 'No execution routes published', 'status-warn');
      rows.push(['Execution API', trading ? 'Routes documented · no order was submitted' : 'No execution routes published', 'status-warn']);
    } else {
      set('contract', 'Unavailable', 'status-bad');
      set('realtime', 'Unknown', 'status-warn');
      set('execution', 'Not verified', 'status-warn');
      rows.push(['API contract', 'Unavailable · check authentication or service response', 'status-bad']);
      rows.push(['Realtime API', 'Not verified', 'status-warn']);
      rows.push(['Execution API', 'Not verified · no order was submitted', 'status-warn']);
    }
    renderRows(rows);
    if (refresh) { refresh.disabled = false; refresh.textContent = 'Refresh status'; }
  }

  function boot() {
    if (!$('[data-api-status-page]')) return;
    $('[data-status-refresh]')?.addEventListener('click', load);
    load();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
