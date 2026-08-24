(() => {
  'use strict';
  if (window.__algoBotStrategyCenter) return;
  window.__algoBotStrategyCenter = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let strategies = [];

  const connected = () => {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  };

  function renderBlocked(message) {
    $('[data-s-list]').innerHTML = `<div class="empty-state">${esc(message)}</div>`;
    $('[data-s-strategy-signals]').innerHTML = `<div class="empty-state">${esc(message)}</div>`;
    $('[data-s-performance]').innerHTML = `<div class="empty-state">${esc(message)}</div>`;
    ['[data-s-total]', '[data-s-enabled]', '[data-s-running]', '[data-s-signals]'].forEach(selector => { const node = $(selector); if (node) node.textContent = '—'; });
  }

  function render() {
    const query = String($('[data-s-search]')?.value || '').toLowerCase();
    const visible = strategies.filter(strategy => String(strategy.name || strategy.slug || '').toLowerCase().includes(query));
    $('[data-s-total]').textContent = strategies.length;
    $('[data-s-enabled]').textContent = strategies.filter(strategy => strategy.enabled).length;
    $('[data-s-running]').textContent = strategies.filter(strategy => strategy.lifecycle_state === 'running').length;
    $('[data-s-list]').innerHTML = visible.length ? visible.map(strategy => `<article class="strategy-row" data-name="${esc(String(strategy.name || strategy.slug).toLowerCase())}"><div><strong>${esc(strategy.name || strategy.slug)}</strong><small>${esc(strategy.category || 'Strategy')} · v${esc(strategy.version || '1.0.0')}</small></div><span class="state-badge">${esc(strategy.lifecycle_state || 'created')}</span><span>${strategy.enabled ? 'Enabled' : 'Disabled'}</span><a class="btn small ghost" href="/trading/">Trade</a></article>`).join('') : '<div class="empty-state">No strategies registered by the backend.</div>';
  }

  async function load() {
    if (!connected()) { renderBlocked('Connect a broker before loading executable strategy state.'); return; }
    try {
      const [strategyResponse, signalResponse, performanceResponse] = await Promise.all([
        window.AlgoBotFrontendData.request('/api/strategies/'),
        window.AlgoBotFrontendData.request('/api/strategies/signals/'),
        window.AlgoBotFrontendData.request('/api/strategies/performance/')
      ]);
      strategies = list(strategyResponse);
      const signals = list(signalResponse), performance = list(performanceResponse);
      render();
      $('[data-s-signals]').innerHTML = signals.slice(0, 8).map(signal => `<div class="signal-row"><strong>${esc(signal.symbol)}</strong><span>${esc(signal.signal)}</span><b>${signal.confidence != null ? Number(signal.confidence).toFixed(0) + '%' : 'Unavailable'}</b></div>`).join('') || '<div class="empty-state">No broker-scoped strategy signals.</div>';
      $('[data-s-performance]').innerHTML = performance.slice(0, 8).map(item => `<div class="mini-row"><strong>${esc(item.strategy_name || item.strategy || 'Strategy')}</strong><span>${item.win_rate != null ? Number(item.win_rate).toFixed(1) + '%' : 'Unavailable'}</span><b>${esc(item.net_profit ?? 'Unavailable')}</b></div>`).join('') || '<div class="empty-state">No performance records.</div>';
      $('[data-s-signals]').closest('.panel')?.setAttribute('data-broker-state', window.AlgoBotBrokerState.get().status);
    } catch (error) {
      renderBlocked(`Strategy data unavailable: ${error.message}`);
    }
  }

  async function action(path, body = {}) {
    try {
      window.AlgoBotFrontendData.requireConnected('run or change executable strategies');
      await window.AlgoBotFrontendData.request(path, { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify(body) });
      window.alert('Backend strategy action confirmed.');
      await load();
    } catch (error) { window.alert(error.message); }
  }

  function boot() {
    window.AlgoBotBrokerState?.subscribe(event => {
      if (['NO_BROKER', 'DISCONNECTED'].includes(event.detail.state.status)) renderBlocked('Connect a broker before loading executable strategy state.');
      else if (['READY', 'CONNECTED'].includes(event.detail.state.status)) load();
    });
    document.querySelectorAll('[data-strategy-run]').forEach(button => button.addEventListener('click', () => action('/api/strategies/run/')));
    $('[data-strategy-pause]')?.addEventListener('click', () => action('/api/strategies/pause/'));
    $('[data-strategy-stop]')?.addEventListener('click', () => { if (window.confirm('Stop all active strategies?')) action('/api/strategies/stop/'); });
    $('[data-s-search]')?.addEventListener('input', render);
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once:true });
  else boot();
})();
