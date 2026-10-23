/* Contract tests: node static/js/market_asset_registry.test.js */
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('static/js/market_asset_registry.js', 'utf8');
const context = {window: {}};
vm.runInNewContext(source, context);
const api = context.window.AlgoBotMarketAssets;
function assert(condition, message) { if (!condition) throw new Error(message); }
const current = api.normalise({underlying_symbol:'frxEURUSD',underlying_symbol_name:'EUR/USD',underlying_symbol_type:'forex',market:'forex'});
assert(current.symbol === 'frxEURUSD' && current.displayName === 'EUR/USD', 'normalizes current Deriv field names');
const legacy = api.normalise({symbol:'frxEURUSD',display_name:'EUR/USD',symbol_type:'forex'});
assert(legacy.symbol === current.symbol && legacy.displayName === current.displayName, 'normalizes legacy Deriv fields');
const pair = api.resolve({underlying_symbol:'frxEURUSD',underlying_symbol_name:'EUR/USD'});
assert(pair.status === 'mapped' && pair.asset.type === 'forex-pair', 'uses remote currency flags for forex pair');
assert(pair.asset.base.flag === 'https://flagcdn.com/eu.svg' && pair.asset.quote.flag === 'https://flagcdn.com/us.svg', 'uses authentic remote country flag URLs');
assert(api.renderIcon({symbol:'frxEURUSD'}).includes('https://flagcdn.com/eu.svg'), 'shared renderer uses remote flag assets');
assert(api.resolve({symbol:'CRYBTCUSD'}).status === 'verified', 'exact crypto symbol has source-attributed icon');
assert(api.resolve({symbol:'CRYBTCUSD'}).asset.src === 'https://cdn.simpleicons.org/bitcoin', 'crypto icon is fetched from upstream CDN');
assert(api.renderIcon({symbol:'CRYBTCUSD'}).includes('https://cdn.simpleicons.org/bitcoin'), 'shared renderer uses upstream remote icon');
for (const symbol of ['R_10','R_25','R_50','R_75','R_100','1HZ10V','1HZ15V','1HZ30V','1HZ50V','1HZ75V','1HZ90V','1HZ100V','RDBULL','RDBEAR','RB_100','RB_200','BOOM1000','CRASH1000','frxXAUUSD','AAPL','CRYAVAXUSD']) {
  assert(api.resolve({symbol}).status === 'missing', symbol + ' must not receive fabricated or guessed artwork');
  assert(api.renderIcon({symbol}).includes('market-avatar-unmapped'), symbol + ' uses neutral fallback until a source asset is verified');
}
assert(api.resolve({symbol:'BTCUSD',market:'cryptocurrency'}).asset === null, 'aliases do not inherit another symbol logo');
assert(api.resolve({symbol:'XAUUSD',market:'commodities'}).family === 'commodities', 'classifies commodities');
assert(api.resolve({symbol:'AAPL',market:'stock'}).family === 'stocks-and-indices', 'classifies equities without inventing artwork');
assert(api.resolve({symbol:'RB_100'}).family === 'synthetic-indices', 'classifies Range Break indices without artwork');
const report = api.coverage([{symbol:'frxEURUSD'},{symbol:'CRYBTCUSD'},{symbol:'R_100'},{symbol:'AAPL',market:'stock'}]);
assert(report.total === 4 && report.verified === 1 && report.missing === 2 && report.mapped === undefined, 'coverage reports verified source assets and missing instruments');
assert(report.byFamily.forex.mapped === 1 && report.byFamily['synthetic-indices'].missing === 1, 'coverage is split by market family');
assert(report.missingSymbols.length === 2, 'coverage enumerates unmapped symbols');
for (const file of ['static/js/trading_terminal.js','static/js/market_scanner.js','static/js/predictions_workspace_fix.js']) {
  const content = fs.readFileSync(file,'utf8');
  assert(!content.includes("status==='authored'") && !content.includes("status === 'authored'"), file + ' no longer renders generated SVG artwork');
}
assert(!fs.existsSync('static/images/market-assets/synthetic'), 'authored synthetic SVG files removed');
assert(!fs.existsSync('static/images/market-flags'), 'authored local currency SVG files removed');
assert(fs.readFileSync('templates/core/trading.html','utf8').includes('market_asset_registry.js'), 'trading template loads shared registry');
console.log('remote market asset registry contract tests passed');
