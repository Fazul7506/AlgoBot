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
const report = api.coverage([{underlying_symbol:'frxEURUSD'},{symbol:'R_100'}]);
assert(report.total === 2 && report.missing === 1 && report.verified === 1, 'coverage counts mapped forex art but keeps unsupported instruments missing');
console.log('market asset registry contract tests passed');