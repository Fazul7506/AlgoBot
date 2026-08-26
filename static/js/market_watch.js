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
  let selectedMarket = 'All';
  let selectedTimeframe = '';

  const initials = row => String(row.display_name || row.symbol || '?').split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase();
  const avatarPalette = market => {
    const key = String(market || '').toLowerCase();
    if (key.includes('crypto')) return ['#f6a623', '#bb5b12'];
    if (key.includes('forex')) return ['#3c91e6', '#2553a4'];
    if (key.includes('commodity')) return ['#d69e2e', '#8b5b15'];
    if (key.includes('stock')) return ['#8b5cf6', '#5b21b6'];
    if (key.includes('boom') || key.includes('crash')) return ['#ef476f', '#a92333'];
    return ['#ff5a64', '#b5203a'];
  };

  function renderCategories() {
    const root = $('[data-market-categories]');
    if (!root) return;
    const markets = ['All', ...new Set(rows.map(row => row.market).filter(Boolean).sort())];
    root.innerHTML = markets.map(market => `<button type="button" class="${market === selectedMarket ? 'active' : ''}" data-market-category="${esc(market)}">${esc(market)}</button>`).join('');
    root.querySelectorAll('[data-market-category]').forEach(button => button.addEventListener('click', () => {
      selectedMarket = button.dataset.marketCategory;
      renderCategories();
      render();
      refreshQuotes();
    }));
  }

  function render(message = null) {
    const root = $('[data-market-list]');
    if (!root) return;
    if (message) { root.innerHTML = `<div class="empty-state">${esc(message)}</div>`; return; }
    const query = String($('[data-market-search]')?.value || '').toLowerCase();
    const items = rows.filter(row => (selectedMarket === 'All' || row.market === selectedMarket) && JSON.stringify(row).toLowerCase().includes(query)).slice(0, 60);
    root.innerHTML = items.map(row => {
      const [a, b] = avatarPalette(row.market);
      const href = `/trading/?symbol=${encodeURIComponent(row.symbol)}${selectedTimeframe ? `&timeframe=${encodeURIComponent(selectedTimeframe)}` : ''}`;
      return `<article class="market-card" data-symbol="${esc(row.symbol)}"><span class="market-avatar" style="--avatar-a:${a};--avatar-b:${b}" aria-hidden="true">${esc(initials(row))}</span><div class="market-card-copy"><span class="eyebrow">${esc(row.market || 'Broker market')}</span><h2>${esc(row.symbol)}</h2><p>${esc(row.display_name || row.symbol)}</p></div><div class="market-quote"><strong data-quote>Loading broker quote…</strong><span data-bidask>Waiting for live quote</span></div><div class="market-card-actions"><a class="btn primary small" data-trade-symbol="${esc(row.symbol)}" href="${href}">Trade</a></div></article>`;
    }).join('') || '<div class="empty-state">No broker instruments match your search.</div>';
    document.querySelectorAll('[data-trade-symbol]').forEach(link => link.addEventListener('click', () => {
      selectedSymbol = link.dataset.tradeSymbol;
      const top = $('[data-trade-selected]');
      if (top) top.href = `/trading/?symbol=${encodeURIComponent(selectedSymbol)}`;
    }));
  }

  async function quote(symbol) {
    try {
      return await window.AlgoBotFrontendData.request('/api/market/ticks/broker/', { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ symbol }) }, 7000);
    } catch (_) {
      try { return await window.AlgoBotFrontendData.request(`/api/ticks/latest/?symbol=${encodeURIComponent(symbol)}`); } catch (_) { return null; }
    }
  }

  async function refreshQuotes() {
    const cards = [...document.querySelectorAll('[data-symbol]')].slice(0, 12);
    if (!cards.length) return;
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
    rows = list(data).filter(row => row?.is_active !== false && row?.is_tradeable !== false);
    renderCategories();
    render();
    await refreshQuotes();
  }

  async function loadTimeframes() {
    const select = $('[data-market-timeframe]');
    if (!select) return;
    try {
      const data = await window.AlgoBotFrontendData.request('/api/chart/capabilities/');
      const frames = list(data?.timeframes);
      select.innerHTML = frames.length
        ? frames.map(frame => `<option value="${esc(frame.seconds)}">${esc(frame.label)}</option>`).join('')
        : '<option value="">Broker intervals unavailable</option>';
      selectedTimeframe = select.value;
    } catch (_) {
      select.innerHTML = '<option value="">Broker intervals unavailable</option>';
    }
  }

  async function syncBrokerSymbols() {
    const response = await window.AlgoBotFrontendData.request('/api/markets/symbols/sync/', { method:'POST', headers:{ 'Content-Type':'application/json' } }, 10000);
    if (response?.status === 'ok') {
      await loadSymbols();
      return true;
    }
    if (response?.stale) {
      await loadSymbols();
      render('Live broker catalogue refresh is delayed; showing the last known broker catalogue.');
      return false;
    }
    return false;
  }

  async function load() {
    render('Loading broker market catalogue…');
    try {
      // Catalogue loading is independent from the browser-side broker-state cache.
      // The authenticated backend is the source of truth for live broker access.
      await loadSymbols();
      await loadTimeframes();
      try { await syncBrokerSymbols(); } catch (error) {
        console.warn('Broker catalogue synchronization unavailable:', error);
      }
      await loadSymbols();
    } catch (error) {
      render(`Broker market catalogue unavailable: ${error.message}`);
    }
  }

  function boot() {
    $('[data-market-search]')?.addEventListener('input', render);
    $('[data-market-timeframe]')?.addEventListener('change', event => {
      selectedTimeframe = event.target.value;
      render();
    });
    $('[data-market-refresh]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const refreshed = await syncBrokerSymbols();
        if (!refreshed) await loadSymbols();
      } catch (error) {
        render(`Broker catalogue refresh unavailable: ${error.message}`);
      } finally {
        button.disabled = false;
      }
    });
    window.AlgoBotBrokerState?.subscribe(event => {
      const status = event.detail?.state?.status;
      if (['READY', 'CONNECTED', 'SYNCING', 'DEGRADED'].includes(status)) {
        load();
      } else if (['NO_BROKER', 'DISCONNECTED'].includes(status)) {
        // Do not erase a valid cached/backend catalogue merely because the client cache changed state.
        if (!rows.length) render('No broker market catalogue is currently available.');
      }
    });
    load();
    quoteTimer = setInterval(() => {
      if (document.visibilityState === 'visible') refreshQuotes();
    }, 15000);
    window.addEventListener('beforeunload', () => clearInterval(quoteTimer), { once: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
