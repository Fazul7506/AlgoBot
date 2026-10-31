const assert = require('node:assert/strict');
const fs = require('node:fs');

const terminal = fs.readFileSync('static/js/terminal_market_watchdog.js', 'utf8');
const marketWatch = fs.readFileSync('static/js/market_watch.js', 'utf8');

assert.match(terminal, /\/ws\/market-data\//, 'Terminal must consume the shared AlgoBot market stream');
assert.doesNotMatch(terminal, /api\.derivws\.com|ws\.derivws\.com/, 'Terminal must not open a direct broker WebSocket');
assert.match(terminal, /action:\s*'subscribe'/, 'Terminal must subscribe through the shared stream contract');
assert.match(terminal, /data\?\.type !== 'market\.tick'/, 'Terminal must consume normalized market.tick events');
assert.doesNotMatch(marketWatch, /tick\.bid\s*==\s*null[^\n]*\?\s*price/, 'Last price must never be substituted for missing bid');
assert.doesNotMatch(marketWatch, /tick\.ask\s*==\s*null[^\n]*\?\s*price/, 'Last price must never be substituted for missing ask');
assert.match(marketWatch, /tick\.bid\s*==\s*null[^\n]*\?\s*null/, 'Missing bid must remain unavailable');
assert.match(marketWatch, /tick\.ask\s*==\s*null[^\n]*\?\s*null/, 'Missing ask must remain unavailable');

process.stdout.write('Shared market-data and bid/ask provenance contracts passed.\n');
