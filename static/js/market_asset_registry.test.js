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
const apple = api.resolve({symbol:'AAPL', display_name:'Apple Inc', market:'stock'});
assert(apple.status === 'verified', 'AAPL resolves through its exact official Deriv stock SVG');
assert(apple.asset.src === 'https://media.ffycdn.net/eu/deriv/EbzwV8V7sdkDD2hsoJQd.svg', 'AAPL uses the official Apple-specific Deriv SVG');
assert(api.manifestEntries.some(x => x.symbol === 'AAPL.OQ' && x.market === 'stocks-and-indices'), 'stock manifest retains exchange-qualified ticker identity');
const aal = api.resolve({symbol:'AAL', display_name:'American Airlines Group Inc', market:'stock'});
assert(aal.status === 'verified' && aal.asset.src === 'https://media.ffycdn.net/eu/deriv/xKHk2HaxuRu2vzJBbQEk.svg', 'AAL resolves to its distinct official Deriv stock SVG');
assert(api.manifestEntries.every(x => (x.url.startsWith('https://cdn.prod.website-files.com/') || x.url.startsWith('https://media.ffycdn.net/eu/deriv/') || x.url.startsWith('https://raw.githubusercontent.com/deriv-com/deriv-smartcharts/e8243d9cb0f47a3d3dcbd184910d36667eb4b43d/')) && x.url.endsWith('.svg')), 'manifest only contains remote SVGs from Deriv CDN');
for (const symbol of ['CRYETHUSD','CRYLTCUSD','CRYSOLUSD','CRYXRPUSD','CRYDOTUSD','CRYLINKUSD','CRYXLMUSD','CRYDASHUSD','CRYAVAXUSD']) {
  assert(api.resolve({symbol}).status === 'verified', symbol + ' resolves through the official Deriv crypto catalogue');
}
for (const symbol of ['frxXAGEUR','frxXAGUSD','frxXAUEUR','frxXPDUSD','frxXPTUSD']) {
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
for (const symbol of ['CRYNOTINCATALOGUE','CRASH150N','frxNGAS','USOIL']) {
  assert(api.resolve({symbol}).status === 'missing', symbol + ' must remain unmapped until its own official instrument-specific SVG is verified');
  assert(api.renderIcon({symbol}).includes('market-avatar-unmapped'), symbol + ' uses neutral fallback rather than shared or fabricated artwork');
}
// These exact symbols use official, commit-pinned instrument SVGs from Deriv SmartCharts.
for (const [symbol, displayName] of [['RDBULL','Daily Reset Bull Index'],['RDBEAR','Daily Reset Bear Index']]) {
  assert(api.resolve({symbol, display_name:displayName, market:'synthetic'}).status === 'verified',
    symbol + ' resolves by exact API symbol even when Deriv supplies a display-name alias');
}
for (const [symbol, suffix] of [
  ['BOOM50','boom50%20index/boom50%20index.svg'],
  ['BOOM100','boom100%20index/boom100%20index.svg'],
  ['BOOM150','boom150%20index/boom150%20index.svg'],
  ['BOOM200','boom200%20index/boom200%20index.svg'],
  ['CRASH50','crash50%20index/crash50%20index.svg'],
  ['CRASH150','crash150%20index/crash150%20index.svg'],
  ['CRASH600','crash600%20index/crash600%20index.svg'],
  ['RDBEAR','bear%20market/ic-marketbear.svg'],
  ['RDBULL','bull%20market/ic-marketbull.svg']
]) {
  const resolved = api.resolve({symbol, market:'synthetic'});
  assert(resolved.status === 'verified', symbol + ' resolves to official Deriv SmartCharts SVG');
  assert(resolved.asset.src.includes(suffix), symbol + ' resolves to its own instrument-specific SVG');
  assert(resolved.asset.src.startsWith('https://raw.githubusercontent.com/deriv-com/deriv-smartcharts/e8243d9cb0f47a3d3dcbd184910d36667eb4b43d/'), symbol + ' uses the pinned official SmartCharts source');
}
for (const [symbol, name, suffix] of [['WLDEUR','EUR Basket','bpNanTKWJ5JDU6Sydc9D.svg'],['WLDGBP','GBP Basket','WmaK2jWb4kU2uA5pN5St.svg'],['WLDUSD','USD Basket','pyyuRjcSgsPjHKFiQofK.svg'],['WLDXAU','Gold Basket','eDGZPTkJwKGPEcSkN95s.svg']]) {
  const basket = api.resolve({underlying_symbol:symbol, underlying_symbol_name:name, underlying_symbol_type:'forex_basket', market:'basket_index', submarket:'forex_basket'});
  assert(basket.family === 'basket-indices', symbol + ' is classified as a basket index');
  assert(basket.status === 'verified', symbol + ' resolves to its official basket SVG');
  assert(basket.asset.src.endsWith(suffix), symbol + ' uses its exact instrument catalogue asset');
}
const audBasket = api.resolve({underlying_symbol:'WLDAUD', underlying_symbol_name:'AUD Basket', underlying_symbol_type:'forex_basket', market:'basket_index', submarket:'forex_basket'});
assert(audBasket.family === 'basket-indices', 'Deriv AUD Basket uses the basket-index family');
assert(audBasket.status === 'verified', 'AUD Basket resolves to its official catalogue SVG');
assert(audBasket.asset.src === 'https://media.ffycdn.net/eu/deriv/ko79afRJyfjSUyZqXK5a.svg', 'AUD Basket uses the exact official Deriv SVG source');
for (const [symbol, name] of [['BOOM1000','Boom 1000 Index'],['BOOM900','Boom 900 Index'],['BOOM300','Boom 300 Index'],['BOOM500','Boom 500 Index'],['BOOM600','Boom 600 Index'],['CRASH500','Crash 500 Index'],['DEX1500UP','DEX 1500 UP Index'],['DRIFT_SWITCH_10','Drift Switch Index 10']]) {
  const resolved = api.resolve({symbol, display_name:name, market:'synthetic'});
  assert(resolved.family === 'synthetic-indices', symbol + ' is classified as synthetic');
  assert(resolved.status === 'verified', symbol + ' resolves to a genuine Deriv-hosted SVG');
  assert(resolved.asset.src.startsWith('https://media.ffycdn.net/eu/deriv/'), symbol + ' uses official Deriv source');
  if (symbol === 'BOOM900') assert(resolved.asset.src === 'https://media.ffycdn.net/eu/deriv/1efQ7vFdtWrE5Ukwop8y.svg', 'Boom 900 uses its own exact official catalogue SVG');
  if (symbol === 'BOOM1000') assert(resolved.asset.src === 'https://media.ffycdn.net/eu/deriv/gizQHBi5p49igXwLwZQS.svg', 'Boom 1000 uses the exact official catalogue SVG');
  if (symbol === 'BOOM1000') assert(resolved.asset.src !== 'https://media.ffycdn.net/eu/deriv/1efQ7vFdtWrE5Ukwop8y.svg', 'Boom 1000 must never reuse the Boom 900 SVG');
}
// Every recognized synthetic family must stay in the synthetic group even while its
// official instrument-specific SVG is unavailable; never borrow a different family's art.
for (const instrument of [
  {symbol:'JD10', display_name:'Jump 10 Index', market:'synthetic'},
  {symbol:'JD25', display_name:'Jump 25 Index', market:'synthetic'},
  {symbol:'JD50', display_name:'Jump 50 Index', market:'synthetic'},
  {symbol:'JD75', display_name:'Jump 75 Index', market:'synthetic'},
  {symbol:'JD100', display_name:'Jump 100 Index', market:'synthetic'},
  {symbol:'RB_100', display_name:'Range Break 100 Index', market:'synthetic'},
  {symbol:'STP100', display_name:'Step Index', market:'synthetic'},
  {symbol:'STP200', display_name:'Step 200 Index', market:'synthetic'},
  {symbol:'STP300', display_name:'Step 300 Index', market:'synthetic'},
  {symbol:'STP400', display_name:'Step 400 Index', market:'synthetic'},
  {symbol:'STP500', display_name:'Step 500 Index', market:'synthetic'},
  {symbol:'MULTISTEP2', display_name:'Multi Step 2 Index', market:'synthetic'},
  {symbol:'DEX1500UP', display_name:'DEX 1500 UP Index', market:'synthetic'},
  {symbol:'DRIFT_SWITCH_30', display_name:'Drift Switch Index 30', market:'synthetic'}
]) {
  const resolved = api.resolve(instrument);
  assert(resolved.family === 'synthetic-indices', instrument.symbol + ' is classified as synthetic');
  assert(resolved.status === 'verified', instrument.symbol + ' resolves to a source-verified official Deriv SVG');
  assert(resolved.asset.src.startsWith('https://media.ffycdn.net/eu/deriv/'), instrument.symbol + ' uses the official Deriv media CDN');
}
for (const instrument of [
  {symbol:'HYBRID100', display_name:'Hybrid 100 Index', market:'synthetic'},
  {symbol:'TREK_UP', display_name:'Trek Up Index', market:'synthetic'},
  {symbol:'SKEWSTEP2', display_name:'Skew Step 2 Index', market:'synthetic'},
  {symbol:'VSWITCH10', display_name:'Volatility Switch 10 Index', market:'synthetic'}
]) {
  const resolved = api.resolve(instrument);
  assert(resolved.family === 'synthetic-indices', instrument.symbol + ' is classified as synthetic');
  assert(resolved.status === 'missing', instrument.symbol + ' must not receive shared generic or unverified artwork');
  assert(api.renderIcon(instrument).includes('market-avatar-unmapped'), instrument.symbol + ' receives neutral fallback until instrument-specific official artwork is verified');
}
const syncScript = fs.readFileSync('scripts/sync_deriv_market_asset_manifest.py','utf8');
assert(syncScript.includes('load_existing_official_media_entries'), 'manifest sync preserves manually verified modern Deriv synthetic SVG entries');
assert(syncScript.includes('("stocks-and-indices", "stocks")'), 'manifest sync scrapes the official individual-stock catalogue as well as stock indices');
assert(syncScript.includes('("synthetic-indices", "derived-indices/synthetic-indices")'), 'manifest sync scrapes the current official synthetic-indices catalogue');
assert(syncScript.includes('modern_synthetic_catalogue'), 'sync gives the current official synthetic catalogue precedence when available');
assert(syncScript.includes('OFFICIAL_SMARTCHARTS_RAW_PREFIX'), 'sync preserves and validates pinned official SmartCharts SVG mappings');
assert(syncScript.includes('Preserve Deriv') && syncScript.includes('catalogue mapping exactly'), 'sync preserves verified source mappings without inventing asset filenames');
assert(syncScript.includes('asset_url.startswith(OFFICIAL_DERIV_MEDIA_PREFIX)'), 'synthetic and stock sync accept the official Deriv media CDN');
assert(syncScript.includes('"synthetic-indices", "basket-indices", "stocks-and-indices"'), 'sync preserves manually verified official stock SVG entries');
assert(syncScript.includes('symbol, name = match.group(1).strip(), match.group(2).strip()'), 'stock sync preserves exact exchange-qualified ticker symbols');
assert(syncScript.includes('OFFICIAL_DERIV_MEDIA_PREFIX'), 'manifest sync explicitly validates the official Deriv media CDN');
assert(syncScript.includes('def validate_svg_asset(url):'), 'sync verifies fetched asset content, not only URL suffixes');
assert(syncScript.includes('response.read(16384)'), 'sync inspects the actual SVG response body');
assert(syncScript.includes('for asset_url in sorted({item["url"] for item in entries}):'), 'asset validation order is deterministic and duplicate URLs are fetched once');
assert(!syncScript.includes('"generatedAt": __import__("datetime")'), 'manifest output does not contain a volatile generation timestamp');
const report = api.coverage([{symbol:'frxEURUSD'},{symbol:'CRYBTCUSD'},{symbol:'R_100'},{symbol:'AAPL',market:'stock'}]);
assert(report.total === 4 && report.verified === 4 && report.missing === 0, 'coverage counts the newly verified stock SVG alongside authentic Deriv assets');
assert(report.byFamily.forex.mapped === 1 && report.byFamily['synthetic-indices'].mapped === 1, 'coverage reports source assets by market family');
assert(report.missingSymbols.length === 0, 'coverage reports no missing symbols for the four verified sample instruments');
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
// The same verified source registry must be wired into every instrument-list surface.
for (const [file, needles] of [
  ['static/js/market_watch.js', ['AlgoBotMarketAssets', 'renderIcon']],
  ['static/js/market_scanner.js', ['AlgoBotMarketAssets', 'resolve']],
  ['static/js/trading_terminal.js', ['AlgoBotMarketAssets', 'marketArtwork']],
  ['templates/core/markets.html', ['deriv_market_asset_manifest.js', 'market_asset_registry.js']],
  ['templates/core/market_scanner.html', ['deriv_market_asset_manifest.js', 'market_asset_registry.js']],
  ['templates/core/trading.html', ['deriv_market_asset_manifest.js', 'market_asset_registry.js']],
  ['templates/core/predictions.html', ['deriv_market_asset_manifest.js', 'market_asset_registry.js']]
]) {
  const source = fs.readFileSync(file, 'utf8');
  for (const needle of needles) assert(source.includes(needle), file + ' must wire the official market asset registry (' + needle + ')');
  if (file.startsWith('templates/')) {
    assert(source.indexOf('deriv_market_asset_manifest.js') < source.indexOf('market_asset_registry.js'), file + ' must load the manifest before the renderer');
  }
}
for (const instrument of [
  {symbol:'BOOM1000', display_name:'Boom 1000 Index', market:'synthetic'},
  {symbol:'BOOM900', display_name:'Boom 900 Index', market:'synthetic'},
  {symbol:'DEX1500UP', display_name:'DEX 1500 UP Index', market:'synthetic'},
  {symbol:'DRIFT_SWITCH_10', display_name:'Drift Switch Index 10', market:'synthetic'}
]) {
  const icon = api.renderIcon(instrument);
  assert(icon.includes('market-asset-verified') && icon.includes('https://media.ffycdn.net/eu/deriv/'), instrument.symbol + ' renders official Deriv artwork in the shared icon renderer');
  assert(icon.includes('alt=') && icon.includes('loading="lazy"'), instrument.symbol + ' has accessible lazy-loaded icon markup');
}
console.log('official Deriv market SVG registry contract tests passed');
