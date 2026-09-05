/* Terminal market-data truth indicator.
 *
 * Observational only: backend remains authoritative for order/risk execution.
 * Transient quote failures are shown as RETRYING/STALE instead of a persistent
 * red ERROR, while preserving the last verified quote state.
 */
(() => {
  'use strict';
  if (window.__algoBotTerminalMarketStatus) return;
  window.__algoBotTerminalMarketStatus = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const api = (url, options = {}, timeout = 15000) => window.AlgoBotServices?.request?.('market-data', url, options, timeout) || window.AlgoBotFrontendData?.request?.(url, options, timeout);
  let timer = null;
  let retryTimer = null;
  let requestInFlight = false;
  let lastGoodAt = 0;
  let consecutiveFailures = 0;

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

  function scheduleRetry() {
    if (retryTimer) clearTimeout(retryTimer);
    const delay = Math.min(30000, 2000 * Math.pow(2, Math.min(consecutiveFailures - 1, 3)));
    retryTimer = window.setTimeout(() => { retryTimer = null; refresh(); }, delay);
  }

  async function refresh() {
    if (requestInFlight) return;
    const symbol = String($('#symbol')?.value || '').trim();
    const account = $('#account')?.value;
    if (!symbol) { setState('waiting', 'Select a broker instrument'); return; }
    if (!account) { setState('waiting', 'Connect a broker account'); return; }

    requestInFlight = true;
    try {
      const payload = await api(`/api/market/ticks/broker/?symbol=${encodeURIComponent(symbol)}`, {notifyOnError:false}, 15000);
      const quote = payload?.quote ?? payload?.price ?? payload?.bid ?? payload?.ask;
      if (quote == null) throw new Error('Broker returned no usable quote');
      consecutiveFailures = 0;
      lastGoodAt = Date.now();
      const stale = payload?.stale === true;
      const source = payload?.source === 'live_broker_quote' ? 'live broker quote' : 'last known broker quote';
      setState(stale ? 'stale' : 'live', `${source} · ${formatAge(payload?.epoch)}`);
    } catch (error) {
      consecutiveFailures += 1;
      const age = lastGoodAt ? Math.round((Date.now() - lastGoodAt) / 1000) : null;
      if (age != null && age <= 120) {
        setState('stale', `Quote refresh delayed · last verified quote ${age}s ago · retrying`);
      } else {
        setState('retrying', consecutiveFailures > 2 ? 'Broker quote unavailable · retrying automatically' : 'Quote refresh delayed · retrying');
      }
      scheduleRetry();
      window.dispatchEvent(new CustomEvent('algobot:market-data-refresh-failed', {detail: {
        symbol, code: error?.code || 'MARKET_REFRESH_ERROR', message: error?.message || 'Broker quote unavailable', consecutiveFailures
      }}));
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
    timer = window.setInterval(refresh, 10000);
    window.addEventListener('pagehide', () => {
      if (timer) window.clearInterval(timer);
      if (retryTimer) window.clearTimeout(retryTimer);
    }, {once: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
