/* Terminal market-data truth indicator.
 * The chart/watchdog is the primary live-feed owner. The HTTP request is only
 * a fallback when the visible quote has actually gone stale.
 */
(() => {
  'use strict';
  if (window.__algoBotTerminalMarketStatus) return;
  window.__algoBotTerminalMarketStatus = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const api = (url, options = {}, timeout = 15000) => window.AlgoBotServices?.request?.('market-data', url, options, timeout) || window.AlgoBotFrontendData?.request?.(url, options, timeout);
  let timer = null;
  let requestInFlight = false;
  let lifecycleToken = 0;
  let lastGoodAt = 0;
  let lastQuoteMutation = Date.now();
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
    if (root) root.dataset.marketDataState = state;
    if (root) root.dispatchEvent(new CustomEvent('algobot:market-data-state', {detail: {state, detail}}));
  }

  function formatAge(epoch) {
    const seconds = Number(epoch) ? Math.max(0, Date.now() / 1000 - Number(epoch)) : null;
    if (seconds == null || !Number.isFinite(seconds)) return 'age unavailable';
    if (seconds < 1) return 'updated just now';
    if (seconds < 60) return `updated ${Math.round(seconds)}s ago`;
    return `updated ${Math.floor(seconds / 60)}m ago`;
  }

  function refresh(force = false) {
    if (lifecycleToken < 0) return;
    const symbol = String($('#symbol')?.value || '').trim();
    const account = $('#account')?.value;
    if (!symbol) { setState('waiting', 'Select a broker instrument'); return; }
    if (!account) { setState('waiting', 'Connect a broker account'); return; }
    // Realtime broker WebSocket events are authoritative for the visible quote.
    // Do not issue a parallel HTTP quote request: it races the stream and can
    // produce misleading Failed to fetch / retrying states.
    const age = lastGoodAt ? Math.max(0, Math.round((Date.now() - lastGoodAt) / 1000)) : null;
    if (age != null && age <= 10) setState('live', 'live broker quote · updated just now');
    else if (age != null) setState('stale', `Quote stream has not produced a verified tick for ${age}s · use Refresh market`);
    else setState('waiting', 'Waiting for live broker quote…');
  }

  function boot() {
    if (!$('.terminal-page')) return;
    ensurePanel();
    const bid = $('[data-q="bid"]'), ask = $('[data-q="ask"]');
    const observer = new MutationObserver(() => {
      // Quote DOM mutations are visual updates only; broker events advance freshness.
    });
    if (bid) observer.observe(bid, {childList:true, characterData:true, subtree:true});
    if (ask) observer.observe(ask, {childList:true, characterData:true, subtree:true});
    $('#symbol')?.addEventListener('change', () => { lastQuoteMutation = Date.now(); refresh(true); });
    $('#account')?.addEventListener('change', () => { lastQuoteMutation = Date.now(); refresh(true); });
    window.addEventListener('algobot:broker-symbols-loaded', () => refresh(true));
    window.addEventListener('algobot:account-synced', () => refresh(true));
    window.addEventListener('algobot:market-symbol-changed', () => refresh(true));
    window.addEventListener('algobot:market-watchdog-tick', event => { lastQuoteMutation = Date.now(); lastGoodAt = Date.now(); consecutiveFailures = 0; setState('live', `live broker quote · ${event.detail?.symbol || 'broker stream'}`); });
    refresh(true);
    window.addEventListener('pagehide', () => { lifecycleToken++; observer.disconnect(); }, {once:true});
    document.addEventListener('visibilitychange', () => {
      lifecycleToken++;
      if (document.hidden) return;
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
