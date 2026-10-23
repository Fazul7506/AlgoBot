/* AlgoBot symbol-aware market asset registry.
 * Local currency flags are authored SVG assets; they are market-identification artwork,
 * not Deriv-provided official logos. Unknown instruments remain explicitly unmapped.
 */
(() => {
  'use strict';
  const currencies = Object.freeze({
    EUR: {name:'Euro area', flag:'/static/images/market-flags/eur.svg'},
    USD: {name:'United States dollar', flag:'/static/images/market-flags/usd.svg'},
    GBP: {name:'British pound', flag:'/static/images/market-flags/gbp.svg'},
    JPY: {name:'Japanese yen', flag:'/static/images/market-flags/jpy.svg'},
    AUD: {name:'Australian dollar', flag:'/static/images/market-flags/aud.svg'},
    NZD: {name:'New Zealand dollar', flag:'/static/images/market-flags/nzd.svg'},
    CAD: {name:'Canadian dollar', flag:'/static/images/market-flags/cad.svg'},
    CHF: {name:'Swiss franc', flag:'/static/images/market-flags/chf.svg'},
    CNY: {name:'Chinese yuan', flag:'/static/images/market-flags/cny.svg'},
    SEK: {name:'Swedish krona', flag:'/static/images/market-flags/sek.svg'},
    NOK: {name:'Norwegian krone', flag:'/static/images/market-flags/nok.svg'},
    DKK: {name:'Danish krone', flag:'/static/images/market-flags/dkk.svg'},
    SGD: {name:'Singapore dollar', flag:'/static/images/market-flags/sgd.svg'},
    HKD: {name:'Hong Kong dollar', flag:'/static/images/market-flags/hkd.svg'},
    ZAR: {name:'South African rand', flag:'/static/images/market-flags/zar.svg'},
    MXN: {name:'Mexican peso', flag:'/static/images/market-flags/mxn.svg'},
    PLN: {name:'Polish złoty', flag:'/static/images/market-flags/pln.svg'},
    TRY: {name:'Turkish lira', flag:'/static/images/market-flags/try.svg'}
  });
  const registry = Object.freeze({
    "CRYBTCUSD": {src:'/static/images/market-assets/crypto/bitcoin.svg', label:"Bitcoin", source:"https://bitcoin.org", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYETHUSD": {src:'/static/images/market-assets/crypto/ethereum.svg', label:"Ethereum", source:"https://ethereum.org/en/assets/", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYLTCUSD": {src:'/static/images/market-assets/crypto/litecoin.svg', label:"Litecoin", source:"https://litecoin-foundation.org/litecoin-branding-guidelines/", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYDOGEUSD": {src:'/static/images/market-assets/crypto/dogecoin.svg', label:"Dogecoin", source:"https://cryptologos.cc/dogecoin", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYSOLUSD": {src:'/static/images/market-assets/crypto/solana.svg', label:"Solana", source:"https://solana.com/branding", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
    "CRYXRPUSD": {src:'/static/images/market-assets/crypto/ripple.svg', label:"Ripple", source:"https://www.ripple.com/media-kit/", licence:'Simple Icons repository CC0-1.0; trademark rights remain with owner'},
  });

  // Classification is intentionally separate from artwork mapping: identifying a
  // market family never implies that an official logo exists for that instrument.
  const classify = instrument => {
    const text = [instrument.market, instrument.subMarket, instrument.symbolType, instrument.displayName].join(' ').toLowerCase();
    const symbol = instrument.symbol.toUpperCase();
    if (/\bforex\b|\bcurrency\b|foreign exchange/.test(text) || /^FRX[A-Z]{6}$/.test(symbol)) return 'forex';
    if (/synthetic|derived|volatility|boom|crash|jump|step|range break/.test(text) || /^(?:R_\d+|1HZ\d+V|BOOM\d+|CRASH\d+|JUMP\d+|STEP\d+|RDBEAR|RDBULL)/.test(symbol)) return 'synthetic-indices';
    if (/crypt|digital asset/.test(text) || /^(?:CRY|BTC|ETH|LTC|XRP|BCH|ADA|DOGE|SOL|DOT|BNB|TRX|AVAX|LINK|XLM|EOS|DASH|ZEC|XMR)[A-Z0-9/_-]*$/.test(symbol)) return 'cryptocurrency';
    if (/commodit|metal|energy|oil|gas|gold|silver/.test(text) || /^(?:XAU|XAG|XPT|XPD|WTI|BRENT|NGAS|UKOIL|USOIL)/.test(symbol)) return 'commodities';
    if (/stock|equity|share|indices|index/.test(text) || /^(?:STOCK|ETF|[A-Z]{1,5}\.[A-Z]{1,3})/.test(symbol)) return 'stocks-and-indices';
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
    const entry = registry[instrument.symbol.toUpperCase()] || null;
    const family = classify(instrument);
    // Deriv forex symbols use the frx + six-letter ISO currency pair convention.
    const match = /^frx([A-Z]{6})$/i.exec(instrument.symbol);
    const pair = match ? match[1].toUpperCase() : '';
    const base = pair ? currencies[pair.slice(0, 3)] : null;
    const quote = pair ? currencies[pair.slice(3, 6)] : null;
    const forex = base && quote ? {type:'forex-pair', base, quote, source:'AlgoBot-authored SVG currency flags', licence:'Public-domain flag designs; artwork authored in-repository'} : null;
    // Never substitute generic/category artwork for a specific Deriv instrument.
    // Only explicit source-verified symbol mappings or currency-pair flags render.
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
    if (resolved.status === 'verified' && resolved.asset?.src) {
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
  window.AlgoBotMarketAssets = Object.freeze({normalise, resolve, renderIcon, coverage, classify, registry, currencies});
})();