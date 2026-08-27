(() => {
  'use strict';
  const root = document.querySelector('[data-strategy-center]');
  if (!root) return;
  const grid = root.querySelector('[data-strategy-grid]');
  const search = root.querySelector('[data-strategy-search]');
  const type = root.querySelector('[data-strategy-type]');
  const status = root.querySelector('[data-strategy-status]');
  let strategies = [];
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const active = s => Boolean(s.enabled ?? s.is_active ?? s.active ?? s.status === 'active');
  const list = v => Array.isArray(v) ? v : (v?.results || v?.strategies || []);
  function render() {
    const q = String(search?.value || '').toLowerCase().trim();
    const filtered = strategies.filter(s => {
      const haystack = JSON.stringify(s).toLowerCase();
      const kind = String(s.strategy_type || s.type || s.category || '').toUpperCase();
      return (!q || haystack.includes(q)) && (!type.value || kind === type.value) && (!status.value || (status.value === 'active') === active(s));
    });
    grid.innerHTML = filtered.length ? filtered.map(s => {
      const metrics = s.performance_metrics || s.metrics || {};
      const win = metrics.win_rate ?? s.win_rate;
      const trades = metrics.total_trades ?? metrics.trades ?? s.total_trades;
      const name = s.name || s.display_name || s.slug || `Strategy #${s.id ?? '—'}`;
      return `<article class="strategy-card"><div class="strategy-card-head"><div><span class="strategy-type">${esc(s.strategy_type || s.type || s.category || 'CUSTOM')}</span><h2>${esc(name)}</h2></div><span class="strategy-state ${active(s) ? 'active' : 'inactive'}">${active(s) ? 'ACTIVE' : 'INACTIVE'}</span></div><p>${esc(s.description || 'Configured algorithm ready for inspection, testing and controlled deployment.')}</p><div class="strategy-stats"><div><span>Win rate</span><strong>${win == null ? '—' : `${Number(win).toFixed(1)}%`}</strong></div><div><span>Trades</span><strong>${esc(trades ?? '—')}</strong></div><div><span>Timeframe</span><strong>${esc(s.timeframe || '—')}</strong></div></div><div class="strategy-actions"><a class="btn" href="/strategies/builder/?strategy=${encodeURIComponent(s.id ?? '')}">Edit</a><a class="btn" href="/backtesting/?strategy=${encodeURIComponent(s.id ?? '')}">Backtest</a></div></article>`;
    }).join('') : '<div class="empty-state">No strategies match the current filters.</div>';
    root.querySelector('[data-total]').textContent = strategies.length;
    root.querySelector('[data-active]').textContent = strategies.filter(active).length;
    root.querySelector('[data-paper]').textContent = strategies.filter(s => s.paper_only || s.paperOnly).length;
    const rates = strategies.map(s => Number((s.performance_metrics || s.metrics || {}).win_rate ?? s.win_rate)).filter(Number.isFinite);
    root.querySelector('[data-winrate]').textContent = rates.length ? `${(rates.reduce((a,b)=>a+b,0)/rates.length).toFixed(1)}%` : '—';
  }
  async function load() {
    grid.innerHTML = '<div class="empty-state">Loading strategies…</div>';
    try {
      const r = await fetch('/api/strategies/', { credentials:'same-origin', headers:{Accept:'application/json'} });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      strategies = list(await r.json());
      render();
    } catch (e) { grid.innerHTML = `<div class="empty-state">Strategy feed unavailable: ${esc(e.message)}</div>`; }
  }
  [search,type,status].forEach(el => el?.addEventListener('input', render));
  root.querySelector('[data-refresh-strategies]')?.addEventListener('click', load);
  load();
})();
