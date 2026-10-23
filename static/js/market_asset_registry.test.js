/* Contract tests: node static/js/market_asset_registry.test.js */
const fs = require('fs');
const vm = require('vm');
const context = {window: {}};
vm.runInNewContext(fs.readFileSync('static/js/deriv_market_asset_manifest.js', 'utf8'), context);
vm.runInNewContext(fs.readFileSync('static/js/market_asset_registry.js', 'utf8'), context);
const api = context.window.AlgoBotMarketAssets;
function assert(condition, message) { if (!condition) throw new Error(message); }
const current = api.normalise({underlying_symbol:'frxEURUSD',underlying_symbol_name:'EUR/USD',underlying_symbol_type:'forex',market:'forex'});
assert(current.symbol === 'frxEURUSD' && current.displayName === 'EUR/USD', 'normalizes current Deriv fields');
const legacy = api.normalise({symbol:'frxEURUSD',display_name:'EUR/USD',symbol_type:'forex'});
assert(legacy.symbol === current.symbol && legacy.displayName === current.displayName, 'normalizes legacy Deriv fields');
assert(api.manifestEntries.length >= 100, 'loads a broad manifest of source-verified Deriv SVG URLs');
assert(api.manifestEntries.every(x => (x.url.startsWith('https://cdn.prod.website-files.com/') || x.url.startsWith('https://media.ffycdn.net/eu/deriv/')) && x.url.endsWith('.svg')), 'manifest only contains remote SVGs from Deriv CDN');
for (const symbol of ['CRYETHUSD','CRYLTCUSD','CRYSOLUSD','CRYXRPUSD','CRYDOTUSD','CRYLINKUSD','CRYXLMUSD','CRYDASHUSD','CRYAVAXUSD']) {
  assert(api.resolve({symbol}).status === 'verified', symbol + ' resolves through the official Deriv crypto catalogue');
}
for (const symbol of ['frxXAGEUR','frxXAGUSD','frxXAUEUR','frxXPDUSD','frxXPTUSD','frxNGAS']) {
  assert(api.resolve({symbol}).status === 'verified', symbol + ' resolves through the official Deriv commodities catalogue');
}

assert(!api.manifestEntries.some(x => x.url.includes('instruments-placeholder.svg')), 'placeholder icons are excluded');
for (const [symbol, suffix] of [
  ['CRYBTCUSD','market-cryptocurrency-btcusd.svg'],
  ['CRYADAUSD','market-cryptocurrency-adausd.svg'],
  ['CRYBNBUSD','market-cryptocurrency-bnbusd.svg'],
  ['CRYDOGEUSD','market-cryptocurrency-dogusd.svg'],
  ['frxEURUSD','market-forex-eurusd.svg'],
  ['frxAUDCAD','market-forex-audcad.svg'],
  ['frxXAUUSD','market-commodity-goldusd.svg'],
  ['R_10','market-derived-volatility-10.svg'],
  ['R_25','market-derived-volatility-25.svg'],
  ['R_50','market-derived-volatility-50.svg'],
  ['R_75','market-derived-volatility-75.svg'],
  ['R_100','market-derived-volatility-100.svg'],
  ['1HZ10V','market-derived-volatility-10-1s.svg'],
  ['1HZ15V','Volatility%25252015%252520(1s).svg'],
  ['1HZ25V','market-derived-volatility-25-1s.svg'],
  ['1HZ30V','Volatility%25252030%252520(1s).svg'],
  ['1HZ50V','market-derived-volatility-50-1s.svg'],
  ['1HZ75V','market-derived-volatility-75-1s.svg'],
  ['1HZ90V','Volatility%25252090%252520(1s).svg'],
  ['1HZ100V','market-derived-volatility-100-1s.svg']
]) {
  const resolved = api.resolve({symbol});
  assert(resolved.status === 'verified', symbol + ' resolves to an authentic Deriv SVG');
  assert(resolved.asset.src.includes(suffix), symbol + ' uses its exact Deriv-hosted SVG');
}
for (const symbol of ['RDBULL','RDBEAR','RB_100','RB_200','CRASH1000','AAPL','CRYNOTINCATALOGUE']) {
  assert(api.resolve({symbol}).status === 'missing', symbol + ' must remain unmapped instead of receiving a fabricated or unrelated icon');
  assert(api.renderIcon({symbol}).includes('market-avatar-unmapped'), symbol + ' uses neutral fallback');
}
const audBasket = api.resolve({underlying_symbol:'WLDAUD', underlying_symbol_name:'AUD Basket', underlying_symbol_type:'forex_basket', market:'basket_index', submarket:'forex_basket'});
assert(audBasket.family === 'basket-indices', 'Deriv AUD Basket uses the basket-index family');
assert(audBasket.status === 'verified', 'AUD Basket resolves to its official catalogue SVG');
assert(audBasket.asset.src === 'https://media.ffycdn.net/eu/deriv/ko79afRJyfjSUyZqXK5a.svg', 'AUD Basket uses the exact official Deriv SVG source');
for (const [symbol, name] of [['BOOM1000','Boom 1000 Index'],['BOOM300','Boom 300 Index'],['CRASH500','Crash 500 Index'],['DEX1500UP','DEX 1500 UP Index'],['DRIFT_SWITCH_10','Drift Switch Index 10']]) {
  const resolved = api.resolve({symbol, display_name:name, market:'synthetic'});
  assert(resolved.family === 'synthetic-indices', symbol + ' is classified as synthetic');
  assert(resolved.status === 'verified', symbol + ' resolves to a genuine Deriv-hosted SVG');
  assert(resolved.asset.src.startsWith('https://media.ffycdn.net/eu/deriv/'), symbol + ' uses official Deriv source');
}
// Every recognized synthetic family must stay in the synthetic group even while its
// official instrument-specific SVG is unavailable; never borrow a different family's art.
for (const instrument of [
  {symbol:'JD10', display_name:'Jump 10 Index', market:'synthetic'},
  {symbol:'STP100', display_name:'Step 100 Index', market:'synthetic'},
  {symbol:'RB_100', display_name:'Range Break 100 Index', market:'synthetic'},
  {symbol:'HYBRID100', display_name:'Hybrid 100 Index', market:'synthetic'},
  {symbol:'RDBULL', display_name:'Daily Reset Bull Index', market:'synthetic'},
  {symbol:'MULTISTEP2', display_name:'Multi Step 2 Index', market:'synthetic'},
  {symbol:'TREK_UP', display_name:'Trek Up Index', market:'synthetic'},
  {symbol:'SKEWSTEP2', display_name:'Skew Step 2 Index', market:'synthetic'},
  {symbol:'VSWITCH10', display_name:'Volatility Switch 10 Index', market:'synthetic'}
]) {
  const resolved = api.resolve(instrument);
  assert(resolved.family === 'synthetic-indices', instrument.symbol + ' is classified as synthetic');
  assert(resolved.status === 'missing', instrument.symbol + ' must not receive an unverified or unrelated SVG');
  assert(api.renderIcon(instrument).includes('market-avatar-unmapped'), instrument.symbol + ' receives neutral fallback until its official SVG is verified');
}
const syncScript = fs.readFileSync('scripts/sync_deriv_market_asset_manifest.py','utf8');
assert(syncScript.includes('load_existing_official_media_entries'), 'manifest sync preserves manually verified modern Deriv synthetic SVG entries');
assert(syncScript.includes('OFFICIAL_DERIV_MEDIA_PREFIX'), 'manifest sync explicitly validates the official Deriv media CDN');
const report = api.coverage([{symbol:'frxEURUSD'},{symbol:'CRYBTCUSD'},{symbol:'R_100'},{symbol:'AAPL',market:'stock'}]);
assert(report.total === 4 && report.verified === 3 && report.missing === 1, 'coverage counts only authentic Deriv SVGs');
assert(report.byFamily.forex.mapped === 1 && report.byFamily['synthetic-indices'].mapped === 1, 'coverage reports source assets by market family');
assert(report.missingSymbols.length === 1, 'coverage enumerates unmapped symbols');
assert(!fs.existsSync('static/images/market-assets/synthetic') && !fs.existsSync('static/images/market-flags'), 'no locally authored market SVG directories remain');
assert(!fs.readFileSync('static/js/market_asset_registry.js','utf8').includes('cdn.simpleicons.org') && !fs.readFileSync('static/js/market_asset_registry.js','utf8').includes('flagcdn.com'), 'market registry does not fall back to third-party generated or generic icon sources');
for (const file of ['static/js/trading_terminal.js','static/js/market_scanner.js','static/js/predictions_workspace_fix.js']) {
  const content = fs.readFileSync(file,'utf8');
  assert(!content.includes("status==='authored'") && !content.includes("status === 'authored'"), file + ' has no generated artwork path');
}
for (const file of ['templates/core/markets.html','templates/core/predictions.html','templates/core/market_scanner.html','templates/core/trading.html']) {
  const content = fs.readFileSync(file,'utf8');
  assert(content.indexOf('deriv_market_asset_manifest.js') < content.indexOf('market_asset_registry.js'), file + ' loads official source manifest before registry');
}
console.log('official Deriv market SVG registry contract tests passed');
