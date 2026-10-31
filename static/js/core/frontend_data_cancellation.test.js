const assert = require('node:assert/strict');
const fs = require('node:fs');

const client = fs.readFileSync('static/js/core/frontend_data_contract.js', 'utf8');
const analysis = fs.readFileSync('static/js/analysis_workspace.js', 'utf8');

assert.match(client, /function linkExternalAbortSignal/);
assert.match(client, /const externalSignal=options\.signal,cancellable=Boolean\(externalSignal\)/);
assert.match(client, /if\(!cancellable&&inflight\.has\(key\)\)/);
assert.match(client, /externalSignal\?\.aborted/);
assert.match(client, /retryTimer=setTimeout/);
assert.match(analysis, /A\.requestController\?\.abort\(\)/);
assert.match(analysis, /request\(endpoint,\{signal:controller\.signal\}\)/);
assert.match(analysis, /request\(endpoint\.replace\([\s\S]*?\{signal:controller\.signal\}\)/);
assert.match(analysis, /window\.addEventListener\("pagehide"/);

process.stdout.write('Analysis request cancellation and bounded retry contracts passed.\n');
