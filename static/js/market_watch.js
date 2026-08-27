/* Connected-broker market catalogue and quote stream. */
(() => {
  'use strict';
  if (window.__algoBotMarketWatch) return;
  window.__algoBotMarketWatch = true;

  const $ = selector => document.querySelector(selector);
  const list = value => window.AlgoBotFrontendData?.list(value) || [];
  const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '\"':'&quot;', "'":'&#039;' })[c]);
  const money = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: 8}) : 'Unavailable';
  const DERIV_PUBLIC_WS = 'wss://api.derivws.com/trading/v1/options/ws/public';

  let rows = [];
  let selectedSymbol = '';
  let selectedMarket = 'All';
  let selectedTimeframe = '60';
  let quoteSocket = null;
  let quoteReconnect = null;
  let requestId = 2000;

  const initials = row => String(row.display_name || row.symbol || '?').split(/\s+/).map(part => part[0]).join('').slice(0,2).toUpperCase();
  const avatarPalette = market => {
    const key = String(market || '').toLowerCase();
    if (key.includes('crypto')) return ['#f6a623','#bb5b12'];
    if (key.includes('forex')) return ['#3c91e6','#2553a4'];
    if (key.includes('commodity')) return ['#d69e2e','#8b5b15'];
    if (key.includes('stock')) return ['#8b5cf6','#5b21b6'];
    if (key.includes('boom') || key.includes('crash')) return ['#ef476f','#a92333'];
    return ['#ff5a64','#b5203a'];
  };

  function renderCategories() {
    const root = $('[data-market-categories]'); if (!root) return;
    const markets = ['All', ...new Set(rows.map(row => row.market).filter(Boolean).sort())];
    root.innerHTML = markets.map(market => `<button type="button" class="${market === selectedMarket ? 'active' : ''}" data-market-category="${esc(market)}">${esc(market)}</button>`).join('');
    root.querySelectorAll('[data-market-category]').forEach(button => button.addEventListener('click', () => {
      selectedMarket = button.dataset.marketCategory; renderCategories(); render(); connectQuoteStream();
    }));
  }

  function render(message = null) {
    const root = $('[data-market-list]'); if (!root) return;
    if (message) { root.innerHTML = `<div class="empty-state">${esc(message)}</div>`; return; }
    const query = String($('[data-market-search]')?.value || '').toLowerCase();
    const items = rows.filter(row => (selectedMarket === 'All' || row.market === selectedMarket) && JSON.stringify(row).toLowerCase().includes(query)).slice(0,60);
    root.innerHTML = items.map(row => {
      const [a,b] = avatarPalette(row.market);
      const href = `/trading/?symbol=${encodeURIComponent(row.symbol)}${selectedTimeframe ? `&timeframe=${encodeURIComponent(selectedTimeframe)}` : ''}`;
      return `<article class="market-card" data-symbol="${esc(row.symbol)}"><span class="market-avatar" style="--avatar-a:${a};--avatar-b:${b}" aria-hidden="true">${esc(initials(row))}</span><div class="market-card-copy"><span class="eyebrow">${esc(row.market || 'Broker market')}</span><h2>${esc(row.symbol)}</h2><p>${esc(row.display_name || row.symbol)}</p></div><div class="market-quote"><strong data-quote>Connecting to broker…</strong><span data-bidask>Waiting for live broker quote</span></div><div class="market-card-actions"><a class="btn primary small" data-trade-symbol="${esc(row.symbol)}" href="${href}">Trade</a></div></article>`;
    }).join('') || '<div class="empty-state">No broker instruments match your search.</div>';
    document.querySelectorAll('[data-trade-symbol]').forEach(link => link.addEventListener('click', () => {
      selectedSymbol = link.dataset.tradeSymbol;
      const top = $('[data-trade-selected]'); if (top) top.href = `/trading/?symbol=${encodeURIComponent(selectedSymbol)}`;
    }));
  }

  function updateQuote(payload) {
    const tick = payload.tick || {};
    const symbol = String(tick.symbol || payload.echo_req?.ticks || '');
    if (!symbol) return;
    const card = document.querySelector(`[data-symbol="${CSS.escape(symbol)}"]`);
    if (!card) return;
    const price = Number(tick.quote);
    if (!Number.isFinite(price)) return;
    card.querySelector('[data-quote]')?.replaceChildren(document.createTextNode(money(price)));
    card.querySelector('[data-bidask]')?.replaceChildren(document.createTextNode(`Bid ${money(tick.bid ?? price)} · Ask ${money(tick.ask ?? price)} · LIVE`));
  }

  function closeQuoteStream() {
    if (quoteSocket) { try { quoteSocket.close(); } catch (_) {} quoteSocket = null; }
    clearTimeout(quoteReconnect);
  }

  function connectQuoteStream() {
    const cards = [...document.querySelectorAll('[data-symbol]')].slice(0,12);
    if (!cards.length || document.visibilityState !== 'visible') return;
    closeQuoteStream();
    try {
      quoteSocket = new WebSocket(DERIV_PUBLIC_WS);
      quoteSocket.addEventListener('open', () => {
        cards.forEach(card => quoteSocket?.send(JSON.stringify({ticks:card.dataset.symbol,subscribe:1,req_id:++requestId})));
      });
      quoteSocket.addEventListener('message', event => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.error) return;
          if (payload.msg_type === 'tick') updateQuote(payload);
        } catch (_) {}
      });
      quoteSocket.addEventListener('close', () => {
        quoteSocket = null;
        if (document.visibilityState === 'visible') quoteReconnect = setTimeout(connectQuoteStream,2500);
      });
      quoteSocket.addEventListener('error', () => {});
    } catch (_) { quoteReconnect = setTimeout(connectQuoteStream,2500); }
  }

  async function loadSymbols() {
    const data = await window.AlgoBotFrontendData.request('/api/market/broker-catalogue/', {}, 10000);
    rows = list(data?.symbols ?? data).filter(row => row?.is_active !== false && row?.is_tradable !== false);
    if (!rows.length) throw new Error('Connected broker returned no active tradable instruments');
    renderCategories(); render(); connectQuoteStream();
  }

  function loadTimeframes() {
    const select = $('[data-market-timeframe]'); if (!select) return;
    // Chart intervals remain a presentation control; the chart sends the
    // selected integer granularity directly to the connected broker.
    const frames = [[60,'1 minute'],[120,'2 minutes'],[300,'5 minutes'],[600,'10 minutes'],[900,'15 minutes'],[1800,'30 minutes'],[3600,'1 hour'],[7200,'2 hours'],[14400,'4 hours'],[28800,'8 hours'],[86400,'1 day']];
    select.innerHTML = frames.map(frame => `<option value="${frame[0]}">${esc(frame[1])}</option>`).join('');
    selectedTimeframe = select.value || '60';
  }

  async function load() {
    render('Loading connected broker market catalogue…');
    try { loadTimeframes(); await loadSymbols(); }
    catch (error) { render(`Broker market catalogue unavailable: ${error.message}`); }
  }

  function boot() {
    $('[data-market-search]')?.addEventListener('input', () => { render(); connectQuoteStream(); });
    $('[data-market-timeframe]')?.addEventListener('change', event => { selectedTimeframe = event.target.value; render(); });
    $('[data-market-refresh]')?.addEventListener('click', async event => {
      const button = event.currentTarget; button.disabled = true;
      try { await loadSymbols(); }
      catch (error) { if (rows.length) render(); else render(`Broker catalogue refresh unavailable: ${error.message}`); }
      finally { button.disabled = false; }
    });
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') connectQuoteStream(); else closeQuoteStream(); });
    window.addEventListener('beforeunload', closeQuoteStream, {once:true});
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();
})();