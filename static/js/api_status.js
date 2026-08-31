(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const api = (u, o = {}) => window.AlgoBotFrontendData.request(u, o, 10000);
  const set = (key, value, className = '') => {
    const element = $(`[data-status="${key}"]`);
    if (!element) return;
    element.textContent = value;
    element.className = className;
  };

  async function load() {
    try {
      const payload = await api('/api/developer/docs/');
      const document = payload?.openapi ? payload : (payload?.payload?.openapi ? payload.payload : payload);
      const paths = document?.paths || {};
      const operations = Object.values(paths).reduce((total, path) => total + Object.keys(path || {}).filter(method => ['get','post','put','patch','delete','options','head'].includes(method)).length, 0);
      const auth = document?.authentication?.type || (document?.security?.length ? 'Protected' : 'Not declared');
      const realtime = Object.keys(paths).some(path => /websocket|realtime|stream|subscribe/i.test(path));
      const trading = Object.keys(paths).some(path => /trade|order|execution/i.test(path));
      const contract = document?.info?.version || 'unknown';

      set('gateway', operations ? 'Operational' : 'No operations', operations ? 'status-ok' : 'status-warn');
      set('contract', operations ? `Published · ${operations} operations` : 'Empty', operations ? 'status-ok' : 'status-bad');
      set('realtime', realtime ? 'Documented' : 'Not exposed', realtime ? 'status-ok' : 'status-warn');

      const version = $('[data-contract-version]');
      if (version) version.textContent = `OpenAPI ${document?.openapi || 'unknown'} · API ${contract} · ${operations} operations`;

      const list = $('[data-status-list]');
      if (list) {
        const rows = [
          ['API contract', operations ? 'Published' : 'Empty', operations ? 'status-ok' : 'status-bad'],
          ['Authentication', auth, auth === 'Not declared' ? 'status-warn' : 'status-ok'],
          ['Realtime API', realtime ? 'Documented' : 'Not exposed', realtime ? 'status-ok' : 'status-warn'],
          ['Trading surface', trading ? 'Present · execution remains gated' : 'Not exposed', trading ? 'status-warn' : 'status-ok'],
          ['Live execution', 'Safety-gated', 'status-warn']
        ];
        list.innerHTML = rows.map(([label, value, cls]) => `<div class="status-row"><span>${label}</span><strong class="${cls}">${value}</strong></div>`).join('');
      }
    } catch (error) {
      set('gateway', 'Unavailable', 'status-bad');
      set('contract', 'Unavailable', 'status-bad');
      set('realtime', 'Unknown', 'status-warn');
      const list = $('[data-status-list]');
      if (list) list.textContent = `Health check failed: ${error.message}`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('[data-api-status-page]')) return;
    $('[data-status-refresh]')?.addEventListener('click', load);
    load();
  }, { once: true });
})();
