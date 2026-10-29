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
  assert.ok(themeCss.includes('html[data-theme="dark"][data-accent="' + accent + '"] { --accent-foreground:'), 'missing dark foreground token for ' + accent);
}
assert.ok(themeCss.includes('html[data-theme="light"][data-accent] { --accent-foreground:#ffffff; }'));
assert.ok(themeCss.includes('background-color:var(--accent);'));
assert.ok(themeCss.includes('color:var(--accent-foreground,#fff) !important;'));

console.log('Preferences runtime tests passed');


// Contrast-check the actual global accent palette, not only token presence.
function relativeLuminance(hex) {
  const channels = hex.replace('#', '').match(/../g).map(part => parseInt(part, 16) / 255);
  const linear = channels.map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}
function contrastRatio(a, b) {
  const values = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
const accountCss = fs.readFileSync('static/css/account_settings.css', 'utf8');
const palette = {
  cyan: { darkAccent: '#08d7f4', darkText: '#06111f', lightAccent: '#087e91' },
  blue: { darkAccent: '#65a5ff', darkText: '#06111f', lightAccent: '#205fca' },
  teal: { darkAccent: '#37e3c1', darkText: '#06111f', lightAccent: '#087b68' },
  violet: { darkAccent: '#c0a5ff', darkText: '#160b2b', lightAccent: '#6940b4' },
  amber: { darkAccent: '#ffd166', darkText: '#211600', lightAccent: '#8a5100' },
};
for (const [name, values] of Object.entries(palette)) {
  assert.ok(contrastRatio(values.darkAccent, values.darkText) >= 4.5, name + ' dark primary-action contrast must meet WCAG AA');
  assert.ok(contrastRatio(values.lightAccent, '#ffffff') >= 4.5, name + ' light primary-action contrast must meet WCAG AA');
  assert.ok(themeCss.includes('html[data-theme="dark"][data-accent="' + name + '"] { --accent:' + values.darkAccent + '; }'), name + ' dark accent matches the actual global palette');
  assert.ok(themeCss.includes('html[data-theme="light"][data-accent="' + name + '"] { --accent:' + values.lightAccent + '; }'), name + ' light accent matches the actual global palette');
  assert.ok(accountCss.includes('.accent-swatch--' + name + '{background:var(--palette-' + name + ','), name + ' swatch uses a theme-aware palette token');
  assert.ok(themeCss.includes('html[data-theme="dark"][data-accent="' + name + '"] { --accent-foreground:' + values.darkText + '; }'), name + ' uses its contrast-tested dark foreground');
}
assert.ok(themeCss.includes('color:var(--accent-foreground,#06111f);'), 'shared primary actions consume the tested foreground token');
console.log('Theme-aware swatch palette tests passed for all five accents.');
console.log('Accent foreground contrast tests passed (WCAG AA, all five accents in both themes).');
