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
const step100 = api.resolve({symbol:'STP100', display_name:'Step Index', market:'synthetic'});
assert(step100.status === 'verified', 'STP100 resolves to the official Step Index SVG');
assert(step100.asset.src === 'https://media.ffycdn.net/eu/deriv/iHeoSRskrtmfrmvq3SXr.svg', 'STP100 uses the exact official Step Index SVG');
assert(api.manifestEntries.some(x => x.symbol === 'STP100' && x.name === 'Step Index'), 'manifest explicitly records the STP100 symbol identity');
const step100BrokerAlias = api.resolve({symbol:'stpRNG', display_name:'Step Index 100', market:'synthetic'});
assert(step100BrokerAlias.status === 'verified', 'Deriv stpRNG / Step Index 100 resolves to the official Step Index SVG');
assert(step100BrokerAlias.asset.src === step100.asset.src, 'Step Index 100 broker alias uses the exact same official Step Index SVG');
assert(api.renderIcon({symbol:'stpRNG', display_name:'Step Index 100', market:'synthetic'}).includes(step100.asset.src), 'Step Index 100 broker alias renders the official SVG');
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
const analysisMarkets = [
  ['BOOM1000','Boom 1000 Index'],['BOOM150N','Boom 150 Index'],['BOOM300N','Boom 300 Index'],['BOOM50','Boom 50 Index'],['BOOM500','Boom 500 Index'],['BOOM600','Boom 600 Index'],['BOOM900','Boom 900 Index'],
  ['CRASH1000','Crash 1000 Index'],['CRASH150N','Crash 150 Index'],['CRASH300N','Crash 300 Index'],['CRASH50','Crash 50 Index'],['CRASH500','Crash 500 Index'],['CRASH600','Crash 600 Index'],['CRASH900','Crash 900 Index'],
  ['cryBTCUSD','BTC/USD'],['cryETHUSD','ETH/USD'],['RB100','Range Break 100 Index'],['RB200','Range Break 200 Index'],['RDBEAR','Bear Market Index'],['RDBULL','Bull Market Index'],
  ['stpRNG','Step Index 100'],['stpRNG2','Step Index 200'],['stpRNG3','Step Index 300'],['stpRNG4','Step Index 400'],['stpRNG5','Step Index 500'],
  ['JD10','Jump 10 Index'],['JD100','Jump 100 Index'],['JD25','Jump 25 Index'],['JD50','Jump 50 Index'],['JD75','Jump 75 Index'],
  ['1HZ100V','Volatility 100 (1s) Index'],['1HZ10V','Volatility 10 (1s) Index'],['1HZ15V','Volatility 15 (1s) Index'],['1HZ25V','Volatility 25 (1s) Index'],['1HZ30V','Volatility 30 (1s) Index'],['1HZ50V','Volatility 50 (1s) Index'],['1HZ75V','Volatility 75 (1s) Index'],['1HZ90V','Volatility 90 (1s) Index'],
  ['R_10','Volatility 10 Index'],['R_100','Volatility 100 Index'],['R_25','Volatility 25 Index'],['R_50','Volatility 50 Index'],['R_75','Volatility 75 Index']
].map(([symbol,display_name]) => ({symbol,display_name}));
const analysisCoverage = api.coverage(analysisMarkets);
assert(analysisCoverage.missing === 0, 'all 43 synthetic-index and cryptocurrency markets in the Analysis screenshot resolve to verified Deriv SVGs');
const analysisCoverageStepOneHundred = api.resolve({symbol:'stpRNG',display_name:'Step Index 100'});
assert(analysisCoverageStepOneHundred.status === 'verified' && analysisCoverageStepOneHundred.asset.label === 'Step Index', 'Step Index 100 remains mapped to its official Deriv SVG');
const sharedPicker = fs.readFileSync('static/js/market_picker_enhancement.js','utf8');
assert(sharedPicker.includes('option.textContent = name'), 'shared market pickers display human-readable market names');
assert(sharedPicker.includes('AlgoBotMarketAssets?.renderIcon'), 'shared market pickers use the verified Deriv SVG resolver');
assert(sharedPicker.includes('const marketIcon = item'), 'market name cells can use the same verified SVG resolver');
assert(sharedPicker.includes('data-ai-symbol') && sharedPicker.includes('data-symbol'), 'shared market picker coverage includes Analysis, Terminal and AI Predictions');
const baseTemplate = fs.readFileSync('templates/base.html','utf8');
assert(baseTemplate.includes('market_picker_enhancement.js'), 'the shared picker enhancement is installed across AlgoBot pages');
const analysisTemplate = fs.readFileSync('templates/core/analysis.html','utf8');
const analysisWorkspace = fs.readFileSync('static/js/analysis_workspace.js','utf8');
assert(analysisTemplate.includes('analysisMarketIcon') && analysisTemplate.includes('analysis-shared-catalogue2'), 'Analysis loads the updated market picker and shared catalogue assets');
assert(analysisWorkspace.includes("/api/market/catalogue/") && !analysisWorkspace.includes("/analysis/markets/"), 'Analysis uses the same canonical instrument API as Terminal rather than a duplicate catalogue');

const anchoredSelects = fs.readFileSync('static/js/anchored_selects.js','utf8');
const anchoredSelectCss = fs.readFileSync('static/css/anchored_selects.css','utf8');
assert(baseTemplate.includes('anchored_selects.js') && baseTemplate.includes('anchored_selects.css'), 'global anchored select menus are loaded from the shared base template');
assert(anchoredSelects.includes("select:not([multiple]):not([size])"), 'global select enhancement covers standard single-select controls across pages');
assert(!anchoredSelects.includes(':not([data-native-select="true"])'), 'visible selects cannot opt out of anchored menus');
assert(anchoredSelects.includes('isHiddenSyncSelect(select)'), 'only hidden synchronization selects remain native');
assert(anchoredSelectCss.includes('display: none !important'), 'native select rendering is hidden to prevent duplicate controls and Android dialogs');
assert(anchoredSelects.includes("role', 'combobox'") && anchoredSelects.includes("setAttribute('role', 'listbox')"), 'custom dropdowns expose accessible combobox and listbox semantics');
assert(anchoredSelects.includes("AlgoBotMarketAssets?.renderIcon"), 'instrument options use the official Deriv SVG registry');
assert(anchoredSelects.includes("new Event('change', {bubbles:true})"), 'select choices dispatch native change events so existing page logic stays connected');
assert(anchoredSelects.includes("ArrowDown") && anchoredSelects.includes("Escape"), 'anchored dropdowns support keyboard navigation and dismissal');
assert(anchoredSelectCss.includes('.ab-select-menu[hidden]') && anchoredSelectCss.includes('position: absolute'), 'menus are anchored popovers, not platform modal selectors');

const marketRegistry = fs.readFileSync('static/js/market_asset_registry.js','utf8');
const marketPicker = fs.readFileSync('static/js/market_picker_enhancement.js','utf8');
assert(!marketRegistry.includes('const initials ='), 'global market asset fallbacks never generate letter-based initials');
assert(!marketRegistry.includes('data-symbol-fallback'), 'remote SVG failures never substitute ticker letters');
assert(marketRegistry.includes('material-symbols-rounded">show_chart'), 'missing or failed market artwork uses a neutral chart icon globally');
assert(!marketPicker.includes('market-avatar market-avatar-unmapped" aria-hidden="true">•'), 'market picker fallback never renders a text glyph instead of an icon');
assert(marketPicker.includes('material-symbols-rounded">show_chart'), 'all market picker fallback branches use the neutral chart icon');

console.log('official Deriv market SVG registry and global anchored-select contract tests passed');
