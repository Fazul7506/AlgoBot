'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = {};
const document = {
  documentElement: { dataset: {} },
  addEventListener(name, callback) { listeners[name] = callback; },
};
const window = {};
vm.runInNewContext(fs.readFileSync('static/js/core/preferences_runtime.js', 'utf8'), { window, document });
const preferences = window.AlgoBotPreferences;
assert.equal(preferences.intervalMs(1234), 60000, 'defaults to one minute');
document.documentElement.dataset.refreshFrequency = '15s';
assert.equal(preferences.intervalMs(), 15000, 'uses saved data-refresh frequency');
document.documentElement.dataset.autoRefresh = '5m';
assert.equal(preferences.intervalMs(), 300000, 'auto-refresh interval overrides data frequency');
assert.equal(preferences.autoRefreshEnabled(), true);
document.documentElement.dataset.autoRefresh = 'manual';
assert.equal(preferences.autoRefreshEnabled(), false, 'manual mode disables automatic refresh');
listeners['algobot:preferences-loaded']({ detail: { refresh_frequency: '30s', auto_refresh_interval: 'realtime' } });
assert.equal(preferences.intervalMs(), 30000, 'updates cadence after preferences load');
assert.equal(preferences.autoRefreshEnabled(), true);

// Keep the global theme contract present for every supported accent. These source-level
// assertions complement (but do not replace) browser-rendered contrast and visual tests.
const themeCss = fs.readFileSync('static/css/account_preferences_global.css', 'utf8');
for (const accent of ['cyan', 'blue', 'teal', 'violet', 'amber']) {
  assert.match(themeCss, new RegExp('html\\\\[data-theme="dark"\\\\]\\\\[data-accent="' + accent + '"\\\\] \\{ --accent-foreground:'));
}
assert.match(themeCss, /html\\[data-theme="light"\\]\\[data-accent\\] \\{ --accent-foreground:#ffffff; \\}/);
assert.match(themeCss, /background-color:var\\(--accent\\);/);
assert.match(themeCss, /color:var\\(--accent-foreground,#fff\\) !important;/);

console.log('Preferences runtime tests passed');
