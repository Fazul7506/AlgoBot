/* Symbol-aware remote asset registry. No locally authored SVGs; unmapped means no verified source asset. */
(() => {
  'use strict';
  const currencies = Object.freeze({
    EUR: {name:'Euro area', flag:'https://flagcdn.com/eu.svg'},
    USD: {name:'United States dollar', flag:'https://flagcdn.com/us.svg'},
    GBP: {name:'British pound', flag:'https://flagcdn.com/gb.svg'},
    JPY: {name:'Japanese yen', flag:'https://flagcdn.com/jp.svg'},
    AUD: {name:'Australian dollar', flag:'https://flagcdn.com/au.svg'},
    NZD: {name:'New Zealand dollar', flag:'https://flagcdn.com/nz.svg'},
    CAD: {name:'Canadian dollar', flag:'https://flagcdn.com/ca.svg'},
    CHF: {name:'Swiss franc', flag:'https://flagcdn.com/ch.svg'},
    CNY: {name:'Chinese yuan', flag:'https://flagcdn.com/cn.svg'},
    SEK: {name:'Swedish krona', flag:'https://flagcdn.com/se.svg'},
    NOK: {name:'Norwegian krone', flag:'https://flagcdn.com/no.svg'},
    DKK: {name:'Danish krone', flag:'https://flagcdn.com/dk.svg'},
    SGD: {name:'Singapore dollar', flag:'https://flagcdn.com/sg.svg'},
    HKD: {name:'Hong Kong dollar', flag:'https://flagcdn.com/hk.svg'},
    ZAR: {name:'South African rand', flag:'https://flagcdn.com/za.svg'},
    MXN: {name:'Mexican peso', flag:'https://flagcdn.com/mx.svg'},
    PLN: {name:'Polish złoty', flag:'https://flagcdn.com/pl.svg'},
    TRY: {name:'Turkish lira', flag:'https://flagcdn.com/tr.svg'}
  });
  const registry = Object.freeze({
    "CRYBTCUSD": {src:'https://cdn.simpleicons.org/bitcoin', label:"Bitcoin", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYETHUSD": {src:'https://cdn.simpleicons.org/ethereum', label:"Ethereum", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYLTCUSD": {src:'https://cdn.simpleicons.org/litecoin', label:"Litecoin", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYDOGEUSD": {src:'https://cdn.simpleicons.org/dogecoin', label:"Dogecoin", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYSOLUSD": {src:'https://cdn.simpleicons.org/solana', label:"Solana", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYXRPUSD": {src:'https://cdn.simpleicons.org/ripple', label:"Ripple", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYADAUSD": {src:'https://cdn.simpleicons.org/cardano', label:"Cardano", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYDOTUSD": {src:'https://cdn.simpleicons.org/polkadot', label:"Polkadot", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYBNBUSD": {src:'https://cdn.simpleicons.org/binance', label:"Binance", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYLINKUSD": {src:'https://cdn.simpleicons.org/chainlink', label:"Chainlink", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYXLMUSD": {src:'https://cdn.simpleicons.org/stellar', label:"Stellar", source:"https://github.com/simple-icons/simple-icons", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
  });

  const allRegistry = registry;

  // Classification is intentionally separate from artwork mapping: identifying a
  // market family never implies that an official logo exists for that instrument.
  const classify = instrument => {
    const text = [instrument.market, instrument.subMarket, instrument.symbolType, instrument.displayName].join(' ').toLowerCase();
    const symbol = instrument.symbol.toUpperCase();
    if (/commodit|metal|energy|oil|gold|silver/.test(text) || /^(?:XAU|XAG|XPT|XPD|WTI|BRENT|NGAS|UKOIL|USOIL)/.test(symbol) || /^FRX(?:XAU|XAG|XPT|XPD)/.test(symbol)) return 'commodities';
    if (/\bforex\b|\bcurrency\b|foreign exchange/.test(text) || /^FRX[A-Z]{6}$/.test(symbol)) return 'forex';
    if (/synthetic|derived|volatility|boom|crash|jump|step|range break/.test(text) || /^(?:R_\d+|RB_\d+|1HZ\d+V|BOOM\d+|CRASH\d+|JUMP\d+|STEP\d+|RDBEAR|RDBULL)/.test(symbol)) return 'synthetic-indices';
    if (/crypt|digital asset/.test(text) || /^(?:CRY|BTC|ETH|LTC|XRP|BCH|ADA|DOGE|SOL|DOT|BNB|TRX|AVAX|LINK|XLM|EOS|DASH|ZEC|XMR)[A-Z0-9/_-]*$/.test(symbol)) return 'cryptocurrency';
    if (/commodit|metal|energy|oil|gas|gold|silver/.test(text) || /^(?:XAU|XAG|XPT|XPD|WTI|BRENT|NGAS|UKOIL|USOIL)/.test(symbol)) return 'commodities';
    if (/stock|equity|share|indices|index/.test(text) || /^(?:AAPL|STOCK|ETF|[A-Z]{1,5}\.[A-Z]{1,3})/.test(symbol)) return 'stocks-and-indices';
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
  const resolve = raw => {
    const instrument = normalise(raw);
    const entry = allRegistry[instrument.symbol.toUpperCase()] || null;
    const family = classify(instrument);
    // Deriv forex symbols use the frx + six-letter ISO currency pair convention.
    const match = /^frx([A-Z]{6})$/i.exec(instrument.symbol);
    const pair = match ? match[1].toUpperCase() : '';
    const base = pair ? currencies[pair.slice(0, 3)] : null;
    const quote = pair ? currencies[pair.slice(3, 6)] : null;
    const forex = base && quote ? {type:'forex-pair', base, quote, source:'https://flagcdn.com/', licence:'FlagCDN-hosted country flags; source terms apply'} : null;
    // Never substitute generic/category artwork for a specific Deriv instrument.
    // Only source-attributed third-party symbol marks or remote currency flags render.
    const asset = entry ? {...entry, type:'symbol-svg'} : forex || null;
    const status = entry ? 'verified' : forex ? 'mapped' : 'missing';
    return {...instrument, family, asset, status, source: entry?.source || forex?.source || null, licence: entry?.licence || forex?.licence || null};
  };
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const renderIcon = raw => {
    const resolved = resolve(raw);
    const label = resolved.displayName || resolved.symbol || 'Unknown instrument';
    if (resolved.status === 'mapped' && resolved.asset?.type === 'forex-pair') {
      const base = resolved.asset.base, quote = resolved.asset.quote;
      return '<span class="market-asset-pair" role="img" aria-label="' + escapeHtml(base.name + ' / ' + quote.name) + '">' +
        '<img loading="lazy" decoding="async" src="' + escapeHtml(base.flag) + '" alt="' + escapeHtml(base.name + ' flag') + '">' +
        '<img loading="lazy" decoding="async" src="' + escapeHtml(quote.flag) + '" alt="' + escapeHtml(quote.name + ' flag') + '"></span>';
    }
    if ((resolved.status === 'verified') && resolved.asset?.src) {
      return '<img class="market-asset-verified" loading="lazy" decoding="async" src="' + escapeHtml(resolved.asset.src) + '" alt="' + escapeHtml(label) + '">';
    }
    const initials = String(raw?.display_name || label || resolved.symbol).split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
    return '<span class="market-avatar market-avatar-unmapped" aria-hidden="true">' + escapeHtml(initials) + '</span>';
  };
  const coverage = instruments => {
    const rows = Array.from(instruments || [], resolve);
    const verified = rows.filter(row => row.status === 'verified').length;
    const illustrated = rows.filter(row => row.status === 'verified' || row.status === 'mapped').length;
    const byFamily = {};
    rows.forEach(row => {
      if (!byFamily[row.family]) byFamily[row.family] = {total: 0, mapped: 0, missing: 0};
      byFamily[row.family].total += 1;
      if (row.status === 'verified' || row.status === 'mapped') byFamily[row.family].mapped += 1;
      else byFamily[row.family].missing += 1;
    });
    return {total: rows.length, verified, illustrated, missing: rows.length - illustrated, percent: rows.length ? Math.round(illustrated / rows.length * 10000) / 100 : 100, byFamily, missingSymbols: rows.filter(row => row.status === 'missing').map(row => ({symbol: row.symbol, family: row.family}))};
  };
  window.AlgoBotMarketAssets = Object.freeze({normalise, resolve, renderIcon, coverage, classify, registry: allRegistry, currencies});
})();