(() => {
  'use strict';
  const root = document.querySelector('[data-data-center]');
  if (!root || root.dataset.runtimeBound === 'true') return;
  root.dataset.runtimeBound = 'true';

  const rowsEl = root.querySelector('[data-data-rows]');
  const errorEl = root.querySelector('[data-data-error]');
  const updatedEl = root.querySelector('[data-data-updated]');
  const filterEl = root.querySelector('[data-data-filter]');
  const statusEl = root.querySelector('[data-data-status]');
  const limitEl = root.querySelector('[data-data-limit]');
  const services = () => window.AlgoBotServices;
  let rows = [];
  let generation = 0;

  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[c]));
  const fmt = value => Number(value || 0).toLocaleString();
  const age = seconds => seconds == null ? '—' : seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
  const request = (url, options = {}, timeout = 10000) => {
    if (services()?.request) return services().request('market-data', url, options, timeout);
    if (window.AlgoBotFrontendData?.request) return window.AlgoBotFrontendData.request(url, options, timeout);
    return Promise.reject(Object.assign(new Error('The AlgoBot service layer is not ready.'), {code:'SERVICE_RUNTIME_UNAVAILABLE', retryable:true}));
  };

  function render() {
    const query = filterEl?.value.trim().toLowerCase() || '';
    const state = statusEl?.value || 'all';
    const limit = Number(limitEl?.value || 50);
    const visible = rows.filter(r => {
      const haystack = `${r.symbol} ${r.display_name} ${r.market} ${r.sub_market}`.toLowerCase();
      return (!query || haystack.includes(query)) && (state === 'all' || r.status === state);
    }).slice(0, limit);
    if (rowsEl) rowsEl.innerHTML = visible.length ? visible.map(r => `<tr><td><strong>${esc(r.symbol)}</strong><small>${esc(r.display_name)}</small></td><td>${esc(r.market)}${r.sub_market ? `<small>${esc(r.sub_market)}</small>` : ''}</td><td>${fmt(r.tick_count)}</td><td>${fmt(r.candle_count)}</td><td>${r.candle_timeframes?.length ? esc(r.candle_timeframes.join(', ')) : '—'}</td><td>${age(r.latest_age_seconds)}</td><td><span class="data-state ${esc(r.status)}">${esc(String(r.status || '').replace('_', ' '))}</span></td></tr>`).join('') : '<tr><td colspan="7" class="data-empty">No instruments match the current filter.</td></tr>';
  }

  async function load() {
    const current = ++generation;
    if (errorEl) errorEl.hidden = true;
    if (rowsEl) rowsEl.innerHTML = '<tr><td colspan="7" class="data-empty">Loading broker data inventory…</td></tr>';
    try {
      const payload = await request('/api/data-center/quality/', {headers:{'Accept':'application/json'}}, 10000);
      if (current !== generation) return;
      if (!payload || payload.status !== 'ok') throw Object.assign(new Error(payload?.detail || 'Data quality service returned an invalid response.'), {code:payload?.code || 'DATA_QUALITY_UNAVAILABLE'});
      rows = Array.isArray(payload.symbols) ? payload.symbols : [];
      Object.entries(payload.summary || {}).forEach(([key, value]) => { const el = root.querySelector(`[data-stat="${key}"]`); if (el) el.textContent = fmt(value); });
      if (updatedEl) updatedEl.textContent = payload.generated_at ? `Updated ${new Date(payload.generated_at).toLocaleTimeString()}` : 'Updated just now';
      render();
    } catch (err) {
      if (current !== generation) return;
      rows = [];
      if (rowsEl) rowsEl.innerHTML = '<tr><td colspan="7" class="data-empty">Data quality is temporarily unavailable. Retry without leaving this page.</td></tr>';
      if (errorEl) { errorEl.textContent = err?.message || 'Unable to load data quality.'; errorEl.hidden = false; }
      if (updatedEl) updatedEl.textContent = 'Unavailable';
    }
  }

  filterEl?.addEventListener('input', render);
  statusEl?.addEventListener('change', render);
  limitEl?.addEventListener('change', render);
  root.querySelector('[data-data-refresh]')?.addEventListener('click', load);
  window.addEventListener('algobot:account-changed', () => load());
  load();
})();
