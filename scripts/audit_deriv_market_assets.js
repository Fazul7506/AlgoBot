#!/usr/bin/env node
/* Audit current Deriv active symbols against source-verified remote market assets.
 * No assets are generated or downloaded by this script.
 * Usage: node scripts/audit_deriv_market_assets.js [--strict]
 */
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const strict = process.argv.includes('--strict');
const context = { window: {} };
vm.runInNewContext(fs.readFileSync('static/js/deriv_market_asset_manifest.js', 'utf8'), context);
vm.runInNewContext(fs.readFileSync('static/js/market_asset_registry.js', 'utf8'), context);
const assets = context.window.AlgoBotMarketAssets;
const timeoutMs = Number(process.env.DERIV_SYMBOL_AUDIT_TIMEOUT_MS || 15000);
const appId = process.env.DERIV_APP_ID || '1089';

function fetchSymbols() {
  return new Promise((resolve, reject) => {
    if (typeof WebSocket === 'undefined') return reject(new Error('This script requires a Node.js runtime with global WebSocket support (Node 22+).'));
    const ws = new WebSocket('wss://ws.binaryws.com/websockets/v3?app_id=' + encodeURIComponent(appId));
    const timer = setTimeout(() => { try { ws.close(); } catch (_) {} reject(new Error('Timed out waiting for Deriv active_symbols response')); }, timeoutMs);
    ws.addEventListener('open', () => ws.send(JSON.stringify({ active_symbols: 'full' })), { once: true });
    ws.addEventListener('message', event => {
      let message;
      try { message = JSON.parse(String(event.data)); } catch (_) { return; }
      if (message.error) {
        clearTimeout(timer); ws.close();
        reject(new Error(message.error.message || 'Deriv API returned an error'));
        return;
      }
      if (message.msg_type !== 'active_symbols' || !Array.isArray(message.active_symbols)) return;
      clearTimeout(timer); ws.close(); resolve(message.active_symbols);
    });
    ws.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Unable to connect to Deriv WebSocket API')); }, { once: true });
  });
}

(async () => {
  const raw = await fetchSymbols();
  const report = assets.coverage(raw);
  const byFamily = Object.fromEntries(Object.entries(report.byFamily).map(([family, values]) => [family, {
    total: values.total, remoteAssetsOrFlags: values.mapped, missingAuthenticAsset: values.missing,
    coveragePercent: values.total ? Math.round(values.mapped / values.total * 10000) / 100 : 100
  }]));
  console.log(JSON.stringify({
    source: 'Deriv active_symbols full response',
    auditedAt: new Date().toISOString(),
    totalActiveSymbols: report.total,
    verifiedSymbolSpecificRemoteIcons: report.verified,
    forexPairsWithRemoteCountryFlags: report.mapped,
    missingAuthenticAssets: report.missing,
    coveragePercent: report.percent,
    byFamily,
    missingSymbols: report.missingSymbols
  }, null, 2));
  if (strict && report.missing > 0) process.exitCode = 2;
})().catch(error => {
  console.error('Deriv asset coverage audit failed: ' + error.message);
  process.exitCode = 1;
});
