(() => {
  'use strict';
  if (window.__algoBotPortfolioDashboard) return;
  window.__algoBotPortfolioDashboard = true;

  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const money = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : 'Unavailable';

  function connected() {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  }

  function stateView(message) {
    const root = $('[data-portfolio-workspace]');
    if (!root) return;
    root.innerHTML = `<div class="ds-state"><strong>Broker connection required</strong><p>${esc(message)}</p><a class="ds-btn ds-btn--primary" href="/brokers/connect/">Connect broker</a></div>`;
  }

  async function load() {
    if (!connected()) {
      stateView('Portfolio values are derived only from the currently connected broker account and its positions.');
      return;
    }
    const root = $('[data-portfolio-workspace]');
    if (!root) return;
    root.innerHTML = '<div class="ds-state"><strong>Synchronizing broker portfolio…</strong><p>Waiting for broker-backed position data.</p></div>';
    try {
      const [positionsResponse] = await Promise.all([window.AlgoBotFrontendData.request('/api/positions/open/')]);
      const positions = list(positionsResponse);
      const account = window.AlgoBotBrokerState.get().account;
      const currency = account?.currency || '';
      const pnl = positions.reduce((sum, position) => sum + Number(position.profit || 0), 0);
      const exposure = positions.reduce((sum, position) => sum + Math.abs(Number(position.size || 0) * Number(position.current_price || 0)), 0);
      const bySymbol = positions.reduce((map, position) => {
        const symbol = position.symbol || 'Unknown';
        const value = Math.abs(Number(position.size || 0) * Number(position.current_price || 0));
        map[symbol] = (map[symbol] || 0) + value;
        return map;
      }, {});
      const allocation = Object.entries(bySymbol).sort((a, b) => b[1] - a[1]);
      root.innerHTML = `
        <section class="kpi-grid compact" aria-label="Broker portfolio overview">
          <article class="kpi-card"><span>Account balance</span><strong>${esc(currency)} ${money(account?.balance)}</strong></article>
          <article class="kpi-card"><span>Broker equity</span><strong>${esc(currency)} ${money(account?.equity)}</strong></article>
          <article class="kpi-card"><span>Open P/L</span><strong>${esc(currency)} ${money(pnl)}</strong></article>
          <article class="kpi-card"><span>Gross exposure</span><strong>${esc(currency)} ${money(exposure)}</strong></article>
        </section>
        <section class="command-grid">
          <article class="panel"><div class="panel-head"><div><p class="eyebrow">Broker positions</p><h2>Current exposure</h2></div><a href="/positions/">Open positions</a></div>${positions.length ? `<div class="table-wrap"><table class="enterprise-table"><thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Current</th><th>P/L</th></tr></thead><tbody>${positions.slice(0, 20).map(p => `<tr><td>${esc(p.symbol)}</td><td>${esc(p.direction || '—')}</td><td>${esc(p.size ?? '—')}</td><td>${esc(p.current_price ?? '—')}</td><td>${esc(p.profit ?? '—')}</td></tr>`).join('')}</tbody></table></div>` : '<div class="ds-state"><strong>No open positions</strong><p>The connected broker currently reports no open positions.</p></div>'}</article>
          <article class="panel"><div class="panel-head"><div><p class="eyebrow">Allocation</p><h2>Exposure by symbol</h2></div></div>${allocation.length ? `<div class="health-stack">${allocation.map(([symbol, value]) => `<span><b></b>${esc(symbol)} <strong>${esc(currency)} ${money(value)}</strong></span>`).join('')}</div>` : '<div class="ds-state"><strong>No allocation data</strong><p>Allocation appears after the broker reports open positions.</p></div>'}</article>
        </section>`;
    } catch (error) {
      root.innerHTML = `<div class="ds-state ds-state--error"><strong>Portfolio unavailable</strong><p>${esc(error.message)}</p><a class="ds-btn" href="/brokers/connect/">Review broker connection</a></div>`;
    }
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(event => {
      if (['NO_BROKER', 'DISCONNECTED'].includes(event.detail.state.status)) stateView('Broker disconnected. Portfolio values are withheld until the connection is restored.');
      else if (['READY', 'CONNECTED'].includes(event.detail.state.status)) load();
    });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
