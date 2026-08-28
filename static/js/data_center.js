(() => {
  const root = document.querySelector('[data-data-center]');
  if (!root) return;
  const rowsEl = root.querySelector('[data-data-rows]');
  const errorEl = root.querySelector('[data-data-error]');
  const updatedEl = root.querySelector('[data-data-updated]');
  const filterEl = root.querySelector('[data-data-filter]');
  const statusEl = root.querySelector('[data-data-status]');
  const limitEl = root.querySelector('[data-data-limit]');
  let rows = [];

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const fmt = (value) => Number(value || 0).toLocaleString();
  const age = (seconds) => seconds == null ? '—' : seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;

  function render() {
    const query = filterEl.value.trim().toLowerCase();
    const state = statusEl.value;
    const limit = Number(limitEl.value);
    const visible = rows.filter(r => {
      const haystack = `${r.symbol} ${r.display_name} ${r.market} ${r.sub_market}`.toLowerCase();
      return (!query || haystack.includes(query)) && (state === 'all' || r.status === state);
    }).slice(0, limit);
    rowsEl.innerHTML = visible.length ? visible.map(r => `<tr><td><strong>${esc(r.symbol)}</strong><small>${esc(r.display_name)}</small></td><td>${esc(r.market)}${r.sub_market ? `<small>${esc(r.sub_market)}</small>` : ''}</td><td>${fmt(r.tick_count)}</td><td>${fmt(r.candle_count)}</td><td>${r.candle_timeframes.length ? esc(r.candle_timeframes.join(', ')) : '—'}</td><td>${age(r.latest_age_seconds)}</td><td><span class="data-state ${esc(r.status)}">${esc(r.status.replace('_', ' '))}</span></td></tr>`).join('') : '<tr><td colspan="7" class="data-empty">No instruments match the current filter.</td></tr>';
  }

  async function load() {
    errorEl.hidden = true;
    rowsEl.innerHTML = '<tr><td colspan="7" class="data-empty">Loading broker data inventory…</td></tr>';
    try {
      const response = await fetch('/api/data-center/quality/', {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.status !== 'ok') throw new Error(payload.detail || `Data Center request failed (${response.status})`);
      rows = Array.isArray(payload.symbols) ? payload.symbols : [];
      Object.entries(payload.summary || {}).forEach(([key, value]) => { const el = root.querySelector(`[data-stat="${key}"]`); if (el) el.textContent = fmt(value); });
      updatedEl.textContent = payload.generated_at ? `Updated ${new Date(payload.generated_at).toLocaleTimeString()}` : 'Updated just now';
      render();
    } catch (err) {
      rows = [];
      rowsEl.innerHTML = '<tr><td colspan="7" class="data-empty">Data quality is unavailable.</td></tr>';
      errorEl.textContent = err.message || 'Unable to load data quality.';
      errorEl.hidden = false;
      updatedEl.textContent = 'Unavailable';
    }
  }
  filterEl.addEventListener('input', render);
  statusEl.addEventListener('change', render);
  limitEl.addEventListener('change', render);
  root.querySelector('[data-data-refresh]').addEventListener('click', load);
  load();
})();
