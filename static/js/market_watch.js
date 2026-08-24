(() => {
  'use strict';
  if (window.__algoBotMarketWatch) return;
  window.__algoBotMarketWatch = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' })[c]);
  let rows = [];
  let selectedSymbol = '';
  let quoteTimer = null;

  function connected() {
    const state = window.AlgoBotBrokerState?.get();
    return !!state?.account && ['CONNECTED', 'SYNCING', 'READY', 'DEGRADED'].includes(state.status);
  }

  function render(message = null) {
    const root = $('[data-market-list]');
    if (!root) return;
    if (message) { root.innerHTML = `<div class="empty-state">${esc(message)}</div>`; return; }
    const query = String($('[data-market-search]')?.value || '').toLowerCase();
    const items = rows.filter(row => JSON.stringify(row).toLowerCase().includes(query)).slice(0, 60);
    root.innerHTML = items.map(row => `<article class="market-card" data-symbol="${esc(row.symbol)}"><div><span class="eyebrow">${esc(row.market || 'Broker market')}</span><h2>${esc(row.symbol)}</h2><p>${esc(row.display_name || row.symbol)}</p></div><div class="market-quote"><strong data-quote>Waiting for broker quote…</strong><span data-bidask>Broker quote pending</span></div><div class="market-card-actions"><a class="btn primary small" data-trade-symbol="${esc(row.symbol)}" href="/trading/?symbol=${encodeURIComponent(row.symbol)}">Trade</a></div></article>`).join('') || '<div class="empty-state">No broker instruments match your search.</div>';
    document.querySelectorAll('[data-trade-symbol]').forEach(link => link.addEventListener('click', () => { selectedSymbol = link.dataset.tradeSymbol; const top = $('[data-trade-selected]'); if (top) top.href = `/trading/?symbol=${encodeURIComponent(selectedSymbol)}`; }));
  }

  async function quote(symbol) {
    try {
      return await window.AlgoBotFrontendData.request('/api/market/ticks/broker/', { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ symbol }) }, 7000);
    } catch (_) {
      try { return await window.AlgoBotFrontendData.request(`/api/ticks/latest/?symbol=${encodeURIComponent(symbol)}`); } catch (_) { return null; }
    }
  }

  async function refreshQuotes() {
    if (!connected()) return;
    const cards = [...document.querySelectorAll('[data-symbol]')].slice(0, 12);
    let cursor = 0;
    const worker = async () => {
      while (true) {
        const index = cursor++;
        if (index >= cards.length) return;
        const card = cards[index];
        const data = await quote(card.dataset.symbol);
        if (!data) continue;
        const quoteNode = card.querySelector('[data-quote]');
        const bidAsk = card.querySelector('[data-bidask]');
        const price = data.quote ?? data.last_price ?? data.price ?? 'Unavailable';
        if (quoteNode) quoteNode.textContent = price;
        if (bidAsk) bidAsk.textContent = `Bid ${data.bid ?? 'Unavailable'} · Ask ${data.ask ?? 'Unavailable'}${data.stale ? ' · last known' : ''}`;
      }
    };
    await Promise.all(Array.from({ length: Math.min(3, cards.length) }, worker));
  }

  async function loadSymbols() {
    const data = await window.AlgoBotFrontendData.request('/api/markets/symbols/');
    rows = list(data).filter(row => row?.is_active !== false && row?.is_tradable !== false);
    render();
    await refreshQuotes();
  }

  async function syncBrokerSymbols() {
    const response = await window.AlgoBotFrontendData.request('/api/markets/symbols/sync/', { method:'POST', headers:{ 'Content-Type':'application/json' } }, 10000);
    if (response?.status === 'ok') await loadSymbols();
    else if (response?.stale) render('Broker catalogue refresh is delayed; the last known broker catalogue remains visible.');
  }

  async function load() {
    if (!connected()) { render('Connect a broker to load the live market catalogue.'); return; }
    render('Synchronizing broker market catalogue…');
    try { await loadSymbols(); } catch (error) { render(`Broker market catalogue unavailable: ${error.message}`); }
  }

  function boot() {
    $('[data-market-search]')?.addEventListener('input', render);
    $('[data-market-refresh]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try { await syncBrokerSymbols(); } catch (error) { render(`Broker catalogue refresh delayed: ${error.message}`); } finally { button.disabled = false; }
    });
    window.AlgoBotBrokerState?.subscribe(event => {
      if (['NO_BROKER', 'DISCONNECTED'].includes(event.detail.state.status)) render('Connect a broker to load the live market catalogue.');
      else if (['READY', 'CONNECTED'].includes(event.detail.state.status)) load();
    });
    load();
    quoteTimer = setInterval(() => { if (document.visibilityState === 'visible') refreshQuotes(); }, 15000);
    window.addEventListener('beforeunload', () => clearInterval(quoteTimer), { once: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
