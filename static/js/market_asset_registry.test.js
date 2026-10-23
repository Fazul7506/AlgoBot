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
assert(api.renderIcon({symbol:'cryBTCUSD'}).includes('/static/images/market-assets/crypto/bitcoin.svg'), 'shared renderer uses the exact local crypto SVG');
assert(api.renderIcon({symbol:'frxEURUSD'}).includes('/static/images/market-flags/eur.svg') && api.renderIcon({symbol:'frxEURUSD'}).includes('/static/images/market-flags/usd.svg'), 'shared renderer displays both forex flags');
assert(api.renderIcon({symbol:'XAUUSD'}).includes('market-avatar-unmapped'), 'missing artwork uses a neutral fallback instead of a fake logo');
assert(api.resolve({symbol:'R_100'}).status === 'authored' && api.resolve({symbol:'R_100'}).asset.src.endsWith('/r-100.svg'), 'known synthetic index resolves to its own AlgoBot-authored SVG');
assert(api.resolve({symbol:'1HZ50V'}).asset.src.endsWith('/1hz50v.svg'), 'one-second synthetic index resolves to its own SVG');
for (const [symbol, file] of [['1HZ15V','1hz15v.svg'],['1HZ30V','1hz30v.svg'],['1HZ90V','1hz90v.svg'],['RDBULL','rdbull.svg'],['RDBEAR','rdbear.svg'],['RB_100','rb-100.svg'],['RB_200','rb-200.svg'],['BOOM1000','boom1000.svg'],['CRASH1000','crash1000.svg']]) {
  assert(api.resolve({symbol}).status === 'authored' && api.resolve({symbol}).asset.src.endsWith('/' + file), symbol + ' resolves to its own authored SVG');
}
assert(api.renderIcon({symbol:'R_100'}).includes('/static/images/market-assets/synthetic/r-100.svg'), 'shared renderer displays exact-symbol authored synthetic artwork');
const report = api.coverage([
  {underlying_symbol:'frxEURUSD', market:'forex'},
  {symbol:'R_10'},
  {symbol:'cryBTCUSD', market:'cryptocurrency'},
  {symbol:'XAUUSD', market:'commodities'},
  {symbol:'AAPL', market:'stock'}
]);
assert(report.total === 5 && report.missing === 2 && report.verified === 1 && report.authored === 1 && report.illustrated === 3, 'coverage counts exact symbol mappings and mapped forex flags only');
assert(report.byFamily.forex.mapped === 1 && report.byFamily['synthetic-indices'].mapped === 1, 'coverage reports mapped and missing artwork by market family');
assert(api.resolve({symbol:'BTCUSD', market:'cryptocurrency'}).family === 'cryptocurrency', 'classifies crypto instruments without inventing artwork');
assert(api.resolve({symbol:'XAUUSD', market:'commodities'}).family === 'commodities', 'classifies commodity instruments without inventing artwork');
assert(api.resolve({symbol:'AAPL', market:'stock'}).family === 'stocks-and-indices', 'classifies equities from catalogue metadata');
assert(report.missingSymbols.length === 2, 'unmapped symbols are explicitly reported as missing artwork');
assert(api.resolve({symbol:'R_100'}).status === 'authored' && api.resolve({symbol:'R_100'}).asset.src.endsWith('/r-100.svg'), 'known synthetic instruments receive distinct authored artwork');
assert(api.resolve({symbol:'RB_100'}).family === 'synthetic-indices', 'Range Break symbols are classified as synthetic indices without catalogue metadata');
assert(api.resolve({symbol:'frxXAUUSD', market:'commodities'}).family === 'commodities', 'Deriv precious-metal symbols are classified as commodities before the forex prefix rule');
assert(api.resolve({symbol:'frxXAUUSD', market:'commodities'}).status === 'authored' && api.resolve({symbol:'frxXAUUSD'}).asset.src.endsWith('/commodities/gold.svg'), 'gold symbol resolves to its own authored SVG');
assert(api.resolve({symbol:'cryBTCUSD', market:'cryptocurrency'}).status === 'verified' && api.resolve({symbol:'cryBTCUSD'}).asset.src.endsWith('/bitcoin.svg'), 'Deriv Bitcoin symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'cryETHUSD'}).asset.src.endsWith('/ethereum.svg'), 'Deriv Ethereum symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'cryLTCUSD'}).asset.src.endsWith('/litecoin.svg'), 'Deriv Litecoin symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'cryADAUSD'}).asset.src.endsWith('/cardano.svg'), 'Deriv Cardano symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'cryDOTUSD'}).asset.src.endsWith('/polkadot.svg'), 'Deriv Polkadot symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'cryBNBUSD'}).asset.src.endsWith('/binance.svg'), 'Deriv BNB symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'cryLINKUSD'}).asset.src.endsWith('/chainlink.svg'), 'Deriv Chainlink symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'cryXLMUSD'}).asset.src.endsWith('/stellar.svg'), 'Deriv Stellar symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'cryDOGEUSD'}).asset.src.endsWith('/dogecoin.svg'), 'Deriv Dogecoin symbol resolves to its exact local SVG');
assert(api.resolve({symbol:'BTCUSD', market:'cryptocurrency'}).asset === null, 'unsupported aliases do not inherit a different symbol logo');
assert(api.resolve({symbol:'XAUUSD', market:'commodities'}).asset === null, 'commodities remain unmapped until a verified symbol-specific asset exists');
assert(api.resolve({symbol:'AAPL', market:'stock'}).asset === null, 'stocks remain unmapped until a verified symbol-specific asset exists');
const terminalSource = fs.readFileSync('static/js/trading_terminal.js', 'utf8');
const scannerSource = fs.readFileSync('static/js/market_scanner.js', 'utf8');
const predictionsSource = fs.readFileSync('static/js/predictions_workspace_fix.js', 'utf8');
assert(terminalSource.includes("resolved?.status==='authored'"), 'trading terminal renders authored market artwork');
assert(scannerSource.includes("asset?.status === 'authored'"), 'market scanner renders authored market artwork');
assert(predictionsSource.includes("resolved?.status === 'authored'"), 'AI Predictions renders authored market artwork');
assert(fs.readFileSync('templates/core/trading.html', 'utf8').includes('market_asset_registry.js'), 'trading template loads shared market asset registry');
console.log('market asset registry contract tests passed');