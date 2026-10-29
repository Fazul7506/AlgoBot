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
console.log('Preferences runtime tests passed');
