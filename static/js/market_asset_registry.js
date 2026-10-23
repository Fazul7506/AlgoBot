/* AlgoBot symbol-aware market asset registry.
 * Only entries with a verified local asset and recorded provenance are rendered as verified.
 * Unknown symbols are reported as missing; they must never be silently marked as official logos.
 */
(() => {
  'use strict';
  const registry = Object.freeze({
    // Initial verified, locally bundled artwork mappings are added by market category.
    // Keep this registry exact-symbol keyed: never infer a brand from a substring.
  });
  const normalise = raw => {
    const item = typeof raw === 'string' ? {symbol: raw} : (raw || {});
    const symbol = String(item.underlying_symbol || item.symbol || item.underlyingSymbol || '').trim();
    const displayName = String(item.underlying_symbol_name || item.display_name || item.displayName || symbol).trim();
    const symbolType = String(item.underlying_symbol_type || item.symbol_type || item.symbolType || '').trim();
    const market = String(item.market || item.market_type || item.asset_class || '').trim();
    const subMarket = String(item.submarket || item.sub_market || item.subgroup || '').trim();
    return {symbol, displayName, symbolType, market, subMarket};
  };
  const resolve = raw => {
    const instrument = normalise(raw);
    const entry = registry[instrument.symbol] || null;
    return { ...instrument, asset: entry, status: entry ? 'verified' : 'missing', source: entry?.source || null, licence: entry?.licence || null };
  };
  const coverage = instruments => {
    const rows = Array.from(instruments || [], resolve);
    const verified = rows.filter(row => row.status === 'verified').length;
    return {total: rows.length, verified, missing: rows.length - verified, percent: rows.length ? Math.round(verified / rows.length * 10000) / 100 : 100, missingSymbols: rows.filter(row => row.status === 'missing').map(row => row.symbol)};
  };
  window.AlgoBotMarketAssets = Object.freeze({normalise, resolve, coverage, registry});
})();