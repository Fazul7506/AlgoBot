/* Lightweight Node-compatible contract tests: node static/js/market_asset_registry.test.js */
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('static/js/market_asset_registry.js', 'utf8');
const context = {window: {}};
vm.runInNewContext(source, context);
const api = context.window.AlgoBotMarketAssets;
function assert(condition, message) { if (!condition) throw new Error(message); }
const current = api.normalise({underlying_symbol:'frxEURUSD',underlying_symbol_name:'EUR/USD',underlying_symbol_type:'forex',market:'forex'});
assert(current.symbol === 'frxEURUSD', 'normalizes current Deriv symbol field');
assert(current.displayName === 'EUR/USD', 'normalizes current Deriv name field');
const legacy = api.normalise({symbol:'frxEURUSD',display_name:'EUR/USD',symbol_type:'forex'});
assert(legacy.symbol === current.symbol && legacy.displayName === current.displayName, 'normalizes legacy response fields');
const pair = api.resolve({underlying_symbol:'frxEURUSD',underlying_symbol_name:'EUR/USD'});
assert(pair.status === 'mapped' && pair.asset.type === 'forex-pair', 'maps supported Deriv forex pairs to local flag artwork');
assert(pair.asset.base.flag.endsWith('/eur.svg') && pair.asset.quote.flag.endsWith('/usd.svg'), 'uses the correct base and quote currency flags');
const report = api.coverage([
  {underlying_symbol:'frxEURUSD', market:'forex'},
  {symbol:'R_100'},
  {symbol:'BTCUSD', market:'cryptocurrency'},
  {symbol:'XAUUSD', market:'commodities'},
  {symbol:'AAPL', market:'stock'}
]);
assert(report.total === 5 && report.missing === 4 && report.verified === 0 && report.illustrated === 1, 'coverage only counts explicit instrument mappings and mapped forex flags');
assert(report.byFamily.forex.mapped === 1 && report.byFamily['synthetic-indices'].mapped === 0, 'coverage reports mapped and missing artwork by market family');
assert(api.resolve({symbol:'BTCUSD', market:'cryptocurrency'}).family === 'cryptocurrency', 'classifies crypto instruments without inventing artwork');
assert(api.resolve({symbol:'XAUUSD', market:'commodities'}).family === 'commodities', 'classifies commodity instruments without inventing artwork');
assert(api.resolve({symbol:'AAPL', market:'stock'}).family === 'stocks-and-indices', 'classifies equities from catalogue metadata');
assert(report.missingSymbols.length === 4, 'unmapped symbols are explicitly reported as missing artwork');
assert(api.resolve({symbol:'R_100'}).asset === null && api.resolve({symbol:'R_100'}).status === 'missing', 'synthetic instruments do not receive fabricated category art');
assert(api.resolve({symbol:'BTCUSD', market:'cryptocurrency'}).asset === null, 'crypto remains unmapped until a verified symbol-specific asset exists');
assert(api.resolve({symbol:'XAUUSD', market:'commodities'}).asset === null, 'commodities remain unmapped until a verified symbol-specific asset exists');
assert(api.resolve({symbol:'AAPL', market:'stock'}).asset === null, 'stocks remain unmapped until a verified symbol-specific asset exists');
console.log('market asset registry contract tests passed');