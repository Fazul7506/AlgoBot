(() => {
  'use strict';
  if (window.__algoBotMarketWatch) return;
  window.__algoBotMarketWatch = true;

  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[c]));
  const list = value => Array.isArray(value) ? value : [];
  const money = value => value == null || value === '' || !Number.isFinite(Number(value))
    ? 'Unavailable'
    : Number(value).toLocaleString(undefined, { maximumFractionDigits: 8 });

  const storedFavourites = () => {
    try {
      const value = JSON.parse(localStorage.getItem('algobot.market.favourites') || '[]');
      return Array.isArray(value) ? value.filter(Boolean).map(String) : [];
    } catch (_) {
      return [];
    }
  };

  let rows = [];
  const quotes = new Map();
  let selectedMarket = 'All';
  let selectedSort = 'name';
  const favourites = new Set(storedFavourites());
  let socket = null;
  let reconnectTimer = null;
  let staleTimer = null;
  let loadSeq = 0;
  let activeAccountId = window.AlgoBotBrokerState?.get?.()?.account?.id == null ? null : String(window.AlgoBotBrokerState.get().account.id);

  const persist = () => {
    try {
      localStorage.setItem(
        'algobot.market.favourites',
        JSON.stringify([...favourites])
      );
    } catch (_) {}
  };

  const statusText = state => ({
    live: 'LIVE',
    stale: 'STALE',
    unavailable: 'QUOTE UNAVAILABLE'
  }[state] || 'QUOTE UNAVAILABLE');

  const categories = () => {
    const root = $('[data-market-categories]');
    if (!root) return;
    const cats = ['All', ...new Set(rows.map(r => r.market).filter(Boolean).sort())];
    root.innerHTML = cats.map(category =>
      '<button type="button" class="' +
      (category === selectedMarket ? 'active' : '') +
      '" data-market-category="' + esc(category) + '">' +
      esc(category) + '</button>'
    ).join('');
    root.querySelectorAll('[data-market-category]').forEach(button => {
      button.addEventListener('click', () => {
        selectedMarket = button.dataset.marketCategory;
        categories();
        render();
        connect();
      });
    });
  };

  const filtered = () => {
    const query = String($('[data-market-search]')?.value || '').trim().toLowerCase();
    const result = rows.filter(row => {
      const haystack = [
        row.symbol, row.display_name, row.market, row.sub_market
      ].join(' ').toLowerCase();
      return (selectedMarket === 'All' || row.market === selectedMarket) &&
        (!query || haystack.includes(query));
    });
    if (selectedSort === 'favourite') {
      result.sort((a, b) =>
        Number(favourites.has(b.symbol)) - Number(favourites.has(a.symbol)) ||
        String(a.display_name || a.symbol).localeCompare(String(b.display_name || b.symbol))
      );
    } else if (selectedSort === 'price') {
      result.sort((a, b) =>
        (quotes.get(b.symbol)?.price ?? -Infinity) -
        (quotes.get(a.symbol)?.price ?? -Infinity)
      );
    } else {
      result.sort((a, b) =>
        String(a.display_name || a.symbol).localeCompare(String(b.display_name || b.symbol))
      );
    }
    return result.slice(0, 120);
  };

  const summary = () => {
    const visible = filtered();
    const total = $('[data-scanner-total]');
    const fav = $('[data-scanner-favourites]');
    const live = $('[data-scanner-live]');
    const markets = $('[data-scanner-markets]');
    if (total) total.textContent = visible.length;
    if (fav) fav.textContent = rows.filter(row => favourites.has(row.symbol)).length;
    if (live) live.textContent = [...quotes.values()].filter(q => q.state === 'live').length;
    if (markets) markets.textContent = new Set(rows.map(row => row.market).filter(Boolean)).size;
  };

  const render = message => {
    const root = $('[data-market-list]');
    if (!root) return;
    if (message) {
      root.innerHTML = '<div class="market-empty">' + esc(message) + '</div>';
      summary();
      return;
    }

    const items = filtered();
    root.innerHTML = items.map(row => {
      const quote = quotes.get(row.symbol);
      const state = quote?.state || 'unavailable';
      const favourite = favourites.has(row.symbol);
      const href = '/trading/?symbol=' + encodeURIComponent(row.symbol);
      const quoteText = quote && state !== 'unavailable' ? money(quote.price) : 'Unavailable';
      const bidAsk = quote && state !== 'unavailable'
        ? 'Bid ' + money(quote.bid) + ' · Ask ' + money(quote.ask) + ' · ' + statusText(state)
        : 'Waiting for broker market feed';

      return '<article class="market-card ' + (favourite ? 'is-favourite' : '') +
        '" data-symbol="' + esc(row.symbol) + '">' +
        '<button class="icon-btn" type="button" data-favourite="' + esc(row.symbol) +
        '" aria-label="' + (favourite ? 'Remove ' : 'Add ') + esc(row.symbol) +
        ' ' + (favourite ? 'from' : 'to') + ' favourites">' +
        (favourite ? '★' : '☆') + '</button>' +
        '<span class="market-avatar" aria-hidden="true">' +
        esc(String(row.display_name || row.symbol).split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase()) +
        '</span>' +
        '<div class="market-card-copy"><span class="eyebrow">' + esc(row.market || 'Broker market') +
        '</span><h2>' + esc(row.symbol) + '</h2><p>' + esc(row.display_name || row.symbol) +
        '</p></div>' +
        '<div class="market-quote"><strong data-quote>' + quoteText +
        '</strong><span data-bidask>' + esc(bidAsk) + '</span></div>' +
        '<div class="market-card-actions"><a class="btn primary small" href="' + href +
        '">Trade</a></div></article>';
    }).join('') || '<div class="market-empty">No broker instruments match your filters.</div>';

    root.querySelectorAll('[data-favourite]').forEach(button => {
      button.addEventListener('click', () => {
        const symbol = button.dataset.favourite;
        if (favourites.has(symbol)) favourites.delete(symbol);
        else favourites.add(symbol);
        persist();
        render();
        connect();
      });
    });
    summary();
  };

  const markStaleQuotes = () => {
    const cutoff = Date.now() - 15000;
    quotes.forEach((quote, symbol) => {
      if (quote.state === 'live' && quote.receivedAt < cutoff) {
        quote.state = 'stale';
        const card = document.querySelector('[data-symbol="' + CSS.escape(symbol) + '"]');
        if (card) {
          const label = card.querySelector('[data-bidask]');
          if (label) label.textContent = 'Bid ' + money(quote.bid) + ' · Ask ' +
            money(quote.ask) + ' · STALE';
        }
      }
    });
    summary();
  };

  const close = () => {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
    const previous = socket;
    socket = null;
    if (previous) {
      try { previous.close(); } catch (_) {}
    }
  };

  const wsUrl = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return protocol + '//' + window.location.host + '/ws/market-data/';
  };

  const connect = () => {
    const symbols = filtered().slice(0, 12).map(row => row.symbol);
    if (!symbols.length || document.visibilityState !== 'visible') {
      close();
      return;
    }
    close();
    try {
      const ws = new WebSocket(wsUrl());
      socket = ws;
      ws.addEventListener('open', () => {
        if (socket !== ws) return;
        ws.send(JSON.stringify({ action: 'subscribe', symbols }));
      });
      ws.addEventListener('message', event => {
        if (socket !== ws) return;
        try {
          const payload = JSON.parse(event.data);
          if (payload.type !== 'market.tick') return;
          const tick = payload.payload || {};
          const symbol = String(tick.symbol || '');
          const price = tick.quote == null || tick.quote === '' ? NaN : Number(tick.quote);
          if (!symbol || !Number.isFinite(price)) return;
          const bid = tick.bid == null || tick.bid === '' ? price : Number(tick.bid);
          const ask = tick.ask == null || tick.ask === '' ? price : Number(tick.ask);
          quotes.set(symbol, {
            price,
            bid: Number.isFinite(bid) ? bid : price,
            ask: Number.isFinite(ask) ? ask : price,
            state: 'live',
            receivedAt: Date.now()
          });
          const card = document.querySelector('[data-symbol="' + CSS.escape(symbol) + '"]');
          if (card) {
            card.querySelector('[data-quote]')?.replaceChildren(
              document.createTextNode(money(price))
            );
            const quote = quotes.get(symbol);
            card.querySelector('[data-bidask]')?.replaceChildren(
              document.createTextNode(
                'Bid ' + money(quote.bid) + ' · Ask ' + money(quote.ask) + ' · LIVE'
              )
            );
          }
          summary();
        } catch (_) {}
      });
      ws.addEventListener('close', () => {
        if (socket !== ws) return;
        socket = null;
        if (document.visibilityState === 'visible') {
          reconnectTimer = setTimeout(connect, 2500);
        }
      });
      ws.addEventListener('error', () => {
        if (socket !== ws) return;
        try { ws.close(); } catch (_) {}
      });
    } catch (_) {
      reconnectTimer = setTimeout(connect, 2500);
    }
  };

  const loadSymbols = async () => {
    const request = window.AlgoBotFrontendData?.request;
    if (!request) throw new Error('AlgoBot market service is not ready.');
    const seq = ++loadSeq;
    const requestedAccountId = window.AlgoBotBrokerState?.get?.()?.account?.id == null ? null : String(window.AlgoBotBrokerState.get().account.id);
    const data = await request('/api/market/broker-catalogue/', {}, 10000);
    const currentAccountId = window.AlgoBotBrokerState?.get?.()?.account?.id == null ? null : String(window.AlgoBotBrokerState.get().account.id);
    if (seq !== loadSeq || requestedAccountId !== currentAccountId) return;
    rows = list(data?.symbols).filter(
      row => row?.is_active !== false && row?.is_tradable !== false
    );
    const catalogueStatus = $('[data-market-catalogue-status]');
    if (catalogueStatus) catalogueStatus.textContent = data?.stale ? 'Cached catalogue · refresh unavailable' : 'Broker catalogue';
    if (!rows.length) throw new Error('Connected broker returned no active tradable instruments.');
    categories();
    render();
    connect();
  };

  const load = async () => {
    const before = loadSeq;
    render('Loading connected broker market catalogue…');
    try {
      await loadSymbols();
    } catch (error) {
      if (loadSeq !== before + 1) return;
      render('Broker market catalogue unavailable: ' + error.message);
    }
  };

  const boot = () => {
    $('[data-market-search]')?.addEventListener('input', () => {
      render();
      connect();
    });
    $('[data-market-sort]')?.addEventListener('change', event => {
      selectedSort = event.target.value;
      render();
      connect();
    });
    $('[data-market-refresh]')?.addEventListener('click', async event => {
      event.currentTarget.disabled = true;
      const before = loadSeq;
      try {
        await loadSymbols();
      } catch (error) {
          if (loadSeq !== before + 1) return;
          if (rows.length) render();
          else render('Broker catalogue refresh unavailable: ' + error.message);
      } finally {
        event.currentTarget.disabled = false;
      }
    });
    window.AlgoBotBrokerState?.subscribe?.(() => {
      const account = window.AlgoBotBrokerState?.get?.()?.account;
      const nextId = account?.id == null ? null : String(account.id);
      if (nextId === activeAccountId) return;
      activeAccountId = nextId;
      loadSeq += 1;
      close();
      rows = [];
      quotes.clear();
      selectedMarket = 'All';
      categories();
      render('Account changed. Loading the selected broker market catalogue…');
      if (nextId) load();
      else if ($('[data-market-catalogue-status]')) $('[data-market-catalogue-status]').textContent = 'No selected broker';
    });
    document.addEventListener('visibilitychange', () =>
      document.visibilityState === 'visible' ? connect() : close()
    );
    window.addEventListener('beforeunload', () => {
      clearInterval(staleTimer);
      close();
    }, { once: true });
    staleTimer = setInterval(markStaleQuotes, 5000);
    load();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
