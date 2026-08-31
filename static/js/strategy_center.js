(() => {
  'use strict';
  const root = document.querySelector('[data-strategy-center]');
  if (!root) return;
  const grid = root.querySelector('[data-strategy-grid]');
  const search = root.querySelector('[data-strategy-search]');
  const type = root.querySelector('[data-strategy-type]');
  const status = root.querySelector('[data-strategy-status]');
  let strategies = [];
  let current = null;
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const list = v => Array.isArray(v) ? v : (v?.results || v?.strategies || []);
  const configured = s => (s.configurations || []).find(c => c.enabled);
  const isCurrent = s => (s.configurations || []).some(c => c.is_active) || Boolean(current?.strategy?.id === s.id);

  function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function ensureControlPanel() {
    if (root.querySelector('[data-strategy-control-panel]')) return;
    const panel = document.createElement('section');
    panel.className = 'strategy-control-panel';
    panel.setAttribute('data-strategy-control-panel', '');
    panel.innerHTML = `<div><strong>Current strategy:</strong> <span data-current-strategy>Loading…</span> <span data-current-account></span></div>
      <label>Criteria (JSON)<textarea data-criteria rows="5" spellcheck="false">{}</textarea></label>
      <button type="button" class="btn" data-save-criteria>Save criteria</button>
      <span data-control-message role="status" aria-live="polite"></span>`;
    root.insertBefore(panel, grid);
    panel.querySelector('[data-save-criteria]').addEventListener('click', saveCriteria);
  }

  function renderCurrent() {
    ensureControlPanel();
    const name = current?.strategy?.name || current?.strategy?.slug || 'NONE';
    const account = current?.configuration?.broker_account ? ` • account ${current.configuration.broker_account}` : '';
    root.querySelector('[data-current-strategy]').textContent = name;
    root.querySelector('[data-current-account]').textContent = account;
    if (current?.configuration) root.querySelector('[data-criteria]').value = JSON.stringify(current.configuration.criteria || {}, null, 2);
  }

  function render() {
    const q = String(search?.value || '').toLowerCase().trim();
    const selectedType = String(type?.value || '').toUpperCase();
    const selectedStatus = String(status?.value || '');
    const filtered = strategies.filter(s => {
      const haystack = JSON.stringify(s).toLowerCase();
      const kind = String(s.strategy_type || s.type || s.category || '').toUpperCase();
      const active = isCurrent(s);
      return (!q || haystack.includes(q)) && (!selectedType || kind === selectedType) && (!selectedStatus || (selectedStatus === 'active') === active);
    });
    grid.innerHTML = filtered.length ? filtered.map(s => {
      const metrics = s.performance_metrics || s.metrics || {};
      const win = metrics.win_rate ?? s.win_rate;
      const trades = metrics.total_trades ?? metrics.trades ?? s.total_trades;
      const cfg = configured(s);
      const name = s.name || s.display_name || s.slug || `Strategy #${s.id ?? '—'}`;
      return `<article class="strategy-card"><div class="strategy-card-head"><div><span class="strategy-type">${esc(s.strategy_type || s.type || s.category || 'CUSTOM')}</span><h2>${esc(name)}</h2></div><span class="strategy-state ${isCurrent(s) ? 'active' : 'inactive'}">${isCurrent(s) ? 'CURRENT' : 'AVAILABLE'}</span></div><p>${esc(s.description || 'Configured algorithm ready for inspection, testing and controlled deployment.')}</p><div class="strategy-stats"><div><span>Win rate</span><strong>${win == null ? '—' : `${Number(win).toFixed(1)}%`}</strong></div><div><span>Trades</span><strong>${esc(trades ?? '—')}</strong></div><div><span>Timeframe</span><strong>${esc(cfg?.timeframe || '—')}</strong></div></div><div class="strategy-actions"><button type="button" class="btn" data-switch-strategy="${esc(s.id)}" ${!cfg ? 'disabled title="Configure this strategy first"' : ''}>${isCurrent(s) ? 'Current' : 'Switch to this'}</button><a class="btn" href="/strategies/builder/?strategy=${encodeURIComponent(s.id ?? '')}">Configure</a><a class="btn" href="/backtesting/?strategy=${encodeURIComponent(s.id ?? '')}">Backtest</a></div></article>`;
    }).join('') : '<div class="empty-state">No strategies match the current filters.</div>';
    root.querySelector('[data-total]')?.replaceChildren(document.createTextNode(strategies.length));
    root.querySelector('[data-active]')?.replaceChildren(document.createTextNode(strategies.filter(isCurrent).length));
    root.querySelector('[data-paper]')?.replaceChildren(document.createTextNode(strategies.filter(s => s.paper_only || s.paperOnly).length));
    const rates = strategies.map(s => Number((s.performance_metrics || s.metrics || {}).win_rate ?? s.win_rate)).filter(Number.isFinite);
    root.querySelector('[data-winrate]')?.replaceChildren(document.createTextNode(rates.length ? `${(rates.reduce((a,b)=>a+b,0)/rates.length).toFixed(1)}%` : '—'));
    grid.querySelectorAll('[data-switch-strategy]').forEach(button => button.addEventListener('click', () => switchStrategy(button.dataset.switchStrategy)));
  }

  async function api(path, options = {}) {
    const method = String(options.method || 'GET').toUpperCase();
    const headers = {
      'Accept': 'application/json',
      ...(options.body ? {'Content-Type': 'application/json'} : {}),
      ...(method !== 'GET' && method !== 'HEAD' ? {'X-CSRFToken': csrfToken()} : {}),
      ...(options.headers || {}),
    };
    const r = await fetch(path, {...options, method, credentials: 'same-origin', headers});
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || data.message || `HTTP ${r.status}`);
    return data;
  }

  async function loadCurrent() {
    try { current = await api('/api/strategies/current/'); }
    catch (e) { current = null; ensureControlPanel(); root.querySelector('[data-control-message]').textContent = `Current strategy unavailable: ${e.message}`; }
    renderCurrent();
    render();
  }

  async function switchStrategy(id) {
    const button = root.querySelector(`[data-switch-strategy="${CSS.escape(String(id))}"]`);
    if (button) button.disabled = true;
    try {
      await api(`/api/strategies/${encodeURIComponent(id)}/switch/`, {method: 'POST', body: JSON.stringify({})});
      root.querySelector('[data-control-message]').textContent = 'Current strategy switched successfully.';
      await Promise.all([load(), loadCurrent()]);
    } catch (e) { root.querySelector('[data-control-message]').textContent = `Switch failed: ${e.message}`; if (button) button.disabled = false; }
  }

  async function saveCriteria() {
    const message = root.querySelector('[data-control-message]');
    const textarea = root.querySelector('[data-criteria]');
    if (!current?.configuration?.id) { message.textContent = 'Configure and switch a strategy first.'; return; }
    try {
      const criteria = JSON.parse(textarea.value || '{}');
      if (!criteria || Array.isArray(criteria) || typeof criteria !== 'object') throw new Error('Criteria must be a JSON object.');
      await api('/api/strategies/criteria/', {method: 'POST', body: JSON.stringify({configuration_id: current.configuration.id, criteria})});
      message.textContent = 'Criteria saved and will be applied on the next strategy execution.';
      await loadCurrent();
    } catch (e) { message.textContent = `Criteria update failed: ${e.message}`; }
  }

  async function load() {
    grid.innerHTML = '<div class="empty-state">Loading strategies…</div>';
    try {
      const data = await api('/api/strategies/available/');
      strategies = list(data);
      render();
    } catch (e) { grid.innerHTML = `<div class="empty-state">Strategy feed unavailable: ${esc(e.message)}</div>`; }
  }

  ensureControlPanel();
  [search, type, status].forEach(el => el?.addEventListener('input', render));
  root.querySelector('[data-refresh-strategies]')?.addEventListener('click', () => Promise.all([load(), loadCurrent()]));
  load();
  loadCurrent();
})();
