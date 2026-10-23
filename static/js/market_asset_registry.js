/* Exact-symbol renderer for remote, source-attributed Deriv SVGs only. */
(() => {
  'use strict';
  const manifest = window.AlgoBotDerivMarketAssetManifest;
  const entries = Array.isArray(manifest?.entries) ? manifest.entries : [];
  const normaliseLabel = value => String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const syntheticNames = Object.freeze({
    R_10:'Volatility 10 Index', R_25:'Volatility 25 Index',
    R_50:'Volatility 50 Index', R_75:'Volatility 75 Index',
    R_100:'Volatility 100 Index',
    BOOM50:'Boom 50 Index', BOOM100:'Boom 100 Index', BOOM150:'Boom 150 Index',
    BOOM200:'Boom 200 Index', BOOM300:'Boom 300 Index', BOOM500:'Boom 500 Index',
    BOOM600:'Boom 600 Index', BOOM900:'Boom 900 Index', BOOM1000:'Boom 1000 Index',
    CRASH500:'Crash 500 Index', DEX1500DOWN:'DEX 1500 DOWN Index', DEX1500UP:'DEX 1500 UP Index',
    DEX600DOWN:'DEX 600 DOWN Index', DEX600UP:'DEX 600 UP Index', DEX900DOWN:'DEX 900 DOWN Index',
    DEX900UP:'DEX 900 UP Index', JD10:'Jump 10 Index', JD25:'Jump 25 Index', JD50:'Jump 50 Index',
    JD75:'Jump 75 Index', JD100:'Jump 100 Index', STP100:'Step Index', STP200:'Step Index 200',
    STP300:'Step Index 300', STP400:'Step Index 400', STP500:'Step Index 500',
    '1HZ10V':'Volatility 10 (1s) Index', '1HZ15V':'Volatility 15 (1s) Index',
    '1HZ25V':'Volatility 25 (1s) Index', '1HZ30V':'Volatility 30 (1s) Index',
    '1HZ50V':'Volatility 50 (1s) Index', '1HZ75V':'Volatility 75 (1s) Index',
    '1HZ90V':'Volatility 90 (1s) Index', '1HZ100V':'Volatility 100 (1s) Index'
  });
  const cryptoAliases = Object.freeze({DOGEUSD:'DOGUSD', AVAXUSD:'AVAUSD', LINKUSD:'LNKUSD', DASHUSD:'DSHUSD'});
  const commodityAliases = Object.freeze({UKOIL:'UK Brent Oil', USOIL:'US Oil'});
  const classify = instrument => {
    const text = [instrument.market, instrument.subMarket, instrument.symbolType, instrument.displayName].join(' ').toLowerCase();
    const symbol = instrument.symbol.toUpperCase();
    if (/basket_index|forex_basket|basket indices|currency basket/.test(text) || /^(?:WLD(?:AUD|EUR|GBP|USD)|WLDCOM|WLDXAU)$/.test(symbol)) return 'basket-indices';
    if (/commodit|metal|energy|oil|gold|silver|palladium|platinum/.test(text) || /^(?:XAU|XAG|XPT|XPD|WTI|BRENT|NGAS|UKOIL|USOIL)/.test(symbol) || /^FRX(?:XAU|XAG|XPT|XPD|NGAS|UKOIL|USOIL)/.test(symbol)) return 'commodities';
    if (/\bforex\b|\bcurrency\b|foreign exchange/.test(text) || /^FRX[A-Z]{6}$/.test(symbol)) return 'forex';
    if (/synthetic|derived|volatility|boom|crash|jump|step|range break|dex|drift|trek|skew|daily reset|multi step|volatility switch|hybrid/.test(text) || /^(?:R_\d+|RB_\d+|1HZ\d+V|BOOM\d+|CRASH\d+|JUMP\d+|JD\d+|STEP\d+|STP\d+|DEX\d+|RDBEAR|RDBULL|DRIFT)/.test(symbol)) return 'synthetic-indices';
    if (/crypt|digital asset/.test(text) || /^(?:CRY|BTC|ETH|LTC|XRP|BCH|ADA|DOGE|SOL|DOT|BNB|TRX|AVAX|LINK|XLM|EOS|DASH|ZEC|XMR)[A-Z0-9/_-]*$/.test(symbol)) return 'cryptocurrency';
    if (/stock|equity|share|indices|index|etf/.test(text) || /^(?:AAPL|STOCK|ETF|[A-Z]{1,5}\.[A-Z]{1,3})/.test(symbol)) return 'stocks-and-indices';
    return 'other';
  };
  const normalise = raw => {
    const item = typeof raw === 'string' ? {symbol: raw} : (raw || {});
    const symbol = String(item.underlying_symbol || item.symbol || item.underlyingSymbol || item.code || '').trim();
    const displayName = String(item.underlying_symbol_name || item.display_name || item.displayName || item.name || symbol).trim();
    const symbolType = String(item.underlying_symbol_type || item.symbol_type || item.symbolType || '').trim();
    const market = String(item.market || item.market_type || item.asset_class || '').trim();
    const subMarket = String(item.submarket || item.sub_market || item.subgroup || '').trim();
    return {symbol, displayName, symbolType, market, subMarket};
  };
  const findOfficialAsset = instrument => {
    const symbol = instrument.symbol.toUpperCase();
    const family = classify(instrument);
    const candidates = [];
    const add = value => { const key = normaliseLabel(value); if (key && !candidates.includes(key)) candidates.push(key); };
    add(instrument.displayName);
    if (family === 'forex' || family === 'commodities') {
      const ticker = symbol.replace(/^FRX/, '');
      add(ticker);
    } else if (family === 'cryptocurrency') {
      const ticker = symbol.replace(/^CRY/, '');
      add(cryptoAliases[ticker] || ticker);
    } else if (family === 'synthetic-indices') {
      add(syntheticNames[symbol]);
      add(syntheticNames[symbol.replace(/[^A-Z0-9]/g, '')]);
    }
    const eligible = entries.filter(item => item.market === family && item.url && item.url.endsWith('.svg'));
    for (const candidate of candidates) {
      const exact = eligible.filter(item => normaliseLabel(item.name) === candidate);
      if (exact.length === 1) return exact[0];
    }
    // Display names can include an added "Index" suffix; only accept a unique longest-prefix match.
    const displayKey = normaliseLabel(instrument.displayName);
    if (displayKey) {
      const matches = eligible.filter(item => {
        const key = normaliseLabel(item.name);
        return key && (displayKey.startsWith(key) || key.startsWith(displayKey));
      }).sort((a,b) => normaliseLabel(b.name).length - normaliseLabel(a.name).length);
      if (matches.length && (matches.length === 1 || normaliseLabel(matches[0].name).length > normaliseLabel(matches[1].name).length)) return matches[0];
    }
    return null;
  };
  const resolve = raw => {
    const instrument = normalise(raw);
    const family = classify(instrument);
    const sourceAsset = findOfficialAsset(instrument);
    const asset = sourceAsset ? {
      src: sourceAsset.url,
      label: sourceAsset.name,
      source: sourceAsset.sourcePage,
      licence: 'Official Deriv-hosted SVG; subject to Deriv terms and trademark rules',
      type: 'symbol-svg',
      artworkKind: 'deriv-official'
    } : null;
    return {...instrument, family, asset, status: asset ? 'verified' : 'missing',
      source: asset?.source || null, licence: asset?.licence || null};
  };
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const renderIcon = raw => {
    const resolved = resolve(raw);
    const label = resolved.displayName || resolved.symbol || 'Unknown instrument';
    if (resolved.status === 'verified' && resolved.asset?.src) {
      return '<img class="market-asset-verified" data-remote-market-asset data-symbol-fallback="' +
        escapeHtml(String(resolved.symbol || '?').slice(0, 2)) + '" loading="lazy" decoding="async" referrerpolicy="no-referrer" src="' +
        escapeHtml(resolved.asset.src) + '" alt="' + escapeHtml(label) + '">';
    }
    const initials = String(label || resolved.symbol).split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
    return '<span class="market-avatar market-avatar-unmapped" aria-hidden="true">' + escapeHtml(initials) + '</span>';
  };
  const coverage = instruments => {
    const rows = Array.from(instruments || [], resolve);
    const verified = rows.filter(row => row.status === 'verified').length;
    const byFamily = {};
    rows.forEach(row => {
      if (!byFamily[row.family]) byFamily[row.family] = {total: 0, mapped: 0, missing: 0};
      byFamily[row.family].total += 1;
      if (row.status === 'verified') byFamily[row.family].mapped += 1;
      else byFamily[row.family].missing += 1;
    });
    return {total: rows.length, verified, illustrated: verified, missing: rows.length - verified,
      percent: rows.length ? Math.round(verified / rows.length * 10000) / 100 : 100,
      byFamily, missingSymbols: rows.filter(row => row.status === 'missing').map(row => ({symbol: row.symbol, family: row.family}))};
  };
  if (typeof document !== 'undefined') {
    document.addEventListener('error', event => {
      const image = event.target;
      if (!(image instanceof HTMLImageElement) || !(image.src.startsWith('https://cdn.prod.website-files.com/') || image.src.startsWith('https://media.ffycdn.net/eu/deriv/'))) return;
      const fallback = document.createElement('span');
      fallback.className = 'market-avatar market-avatar-unmapped';
      fallback.setAttribute('aria-hidden', 'true');
      fallback.textContent = image.getAttribute('data-symbol-fallback') || String(image.alt || '?').trim().slice(0, 2) || '?';
      image.replaceWith(fallback);
    }, true);
  }
  window.AlgoBotMarketAssets = Object.freeze({normalise, resolve, renderIcon, coverage, classify, registry: Object.freeze({}), manifestEntries: entries});
})();