/* Terminal market-data truth indicator.
 *
 * This is intentionally observational in Step 1: it does not replace the
 * existing order/risk pipeline and does not manufacture prices. The backend
 * remains authoritative for whether an order is allowed to execute.
 */
(() => {
  'use strict';
  if (window.__algoBotTerminalMarketStatus) return;
  window.__algoBotTerminalMarketStatus = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const api = (url, options = {}, timeout = 9000) => window.AlgoBotFrontendData?.request?.(url, options, timeout);
  let timer = null;
  let requestInFlight = false;
  let lastSymbol = '';

  function ensurePanel() {
    const toolbar = $('.terminal-toolbar');
    if (!toolbar || $('[data-market-health]')) return $('[data-market-health]');
    const panel = document.createElement('div');
    panel.className = 'market-health';
    panel.dataset.marketHealth = '';
    panel.innerHTML = `
      <span class="market-health-dot" data-market-health-dot aria-hidden="true"></span>
      <span><strong data-market-health-state>CHECKING</strong><small data-market-health-detail>Waiting for broker quote…</small></span>
    `;
    toolbar.appendChild(panel);
    return panel;
  }

  function setState(state, detail) {
    const panel = ensurePanel();
    if (!panel) return;
    panel.dataset.state = state;
    const stateNode = $('[data-market-health-state]', panel);
    const detailNode = $('[data-market-health-detail]', panel);
    if (stateNode) stateNode.textContent = state.toUpperCase();
    if (detailNode) detailNode.textContent = detail || '';
    const root = $('.terminal-page');
    if (root) {
      root.dataset.marketDataState = state;
      root.dispatchEvent(new CustomEvent('algobot:market-data-state', {detail: {state, detail}}));
    }
  }

  function formatAge(epoch) {
    const seconds = Number(epoch) ? Math.max(0, Date.now() / 1000 - Number(epoch)) : null;
    if (seconds == null || !Number.isFinite(seconds)) return 'age unavailable';
    if (seconds < 1) return 'updated just now';
    if (seconds < 60) return `updated ${Math.round(seconds)}s ago`;
    return `updated ${Math.floor(seconds / 60)}m ago`;
  }

  async function refresh() {
    if (requestInFlight) return;
    const symbol = String($('#symbol')?.value || '').trim();
    const account = $('#account')?.value;
    if (!symbol) { setState('waiting', 'Select a broker instrument'); return; }
    if (!account) { setState('waiting', 'Connect a broker account'); return; }

    requestInFlight = true;
    try {
      const payload = await api(`/api/market/ticks/broker/?symbol=${encodeURIComponent(symbol)}`, {}, 9000);
      const quote = payload?.quote ?? payload?.price ?? payload?.bid ?? payload?.ask;
      if (quote == null) throw new Error('Broker returned no usable quote');
      const stale = payload?.stale === true;
      const source = payload?.source === 'live_broker_quote' ? 'live broker quote' : 'last known broker quote';
      const detail = `${source} · ${formatAge(payload?.epoch)}`;
      setState(stale ? 'stale' : 'live', detail);
    } catch (error) {
      setState('error', error?.message || 'Broker quote unavailable');
    } finally {
      requestInFlight = false;
    }
  }

  function boot() {
    if (!$('.terminal-page')) return;
    ensurePanel();
    $('#symbol')?.addEventListener('change', refresh);
    $('#account')?.addEventListener('change', refresh);
    window.addEventListener('algobot:broker-symbols-loaded', refresh);
    window.addEventListener('algobot:account-synced', refresh);
    window.addEventListener('algobot:market-symbol-changed', refresh);
    refresh();
    timer = window.setInterval(() => {
      const symbol = String($('#symbol')?.value || '').trim();
      if (symbol && symbol !== lastSymbol) lastSymbol = symbol;
      refresh();
    }, 3000);
    window.addEventListener('pagehide', () => { if (timer) window.clearInterval(timer); }, {once: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
