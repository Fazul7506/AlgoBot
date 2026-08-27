(() => {
  'use strict';
  if (window.__algoBotDashboardStatus) return;
  window.__algoBotDashboardStatus = true;

  const $ = (selector) => document.querySelector(selector);
  const setStatus = (key, state, text) => {
    const dot = $(`[data-status-dot="${key}"]`);
    const label = $(`[data-status="${key}"]`);
    if (dot) dot.className = `status-dot ${state || ''}`.trim();
    if (label) label.textContent = text;
  };

  function inspect() {
    const balance = $('[data-kpi="balance"]')?.textContent?.trim();
    const broker = $('[data-dashboard-brokers]')?.textContent?.trim() || '';
    const markets = $('[data-dashboard-markets]')?.textContent?.trim() || '';
    const positions = $('[data-dashboard-positions]')?.textContent?.trim() || '';
    const orders = $('[data-dashboard-orders]')?.textContent?.trim() || '';
    const signals = $('[data-dashboard-signals]')?.textContent?.trim() || '';

    if (balance && balance !== 'Unavailable' && !/loading/i.test(balance)) setStatus('account', 'ok', 'Broker account available');
    else if (/no connected|failed|timed out|unavailable/i.test(broker)) setStatus('account', 'error', 'Broker account unavailable');
    else setStatus('account', '', 'Waiting for broker account');

    if (/loading/i.test(markets)) setStatus('markets', '', 'Loading market data');
    else if (/timed out|failed|unavailable/i.test(markets)) setStatus('markets', 'error', 'Market data unavailable');
    else if (/no live market|no market records/i.test(markets)) setStatus('markets', 'warn', 'No live market records');
    else setStatus('markets', 'ok', 'Market data available');

    if (/loading/i.test(positions)) setStatus('positions', '', 'Loading exposure');
    else if (/timed out|failed/i.test(positions)) setStatus('positions', 'error', 'Exposure request failed');
    else setStatus('positions', 'ok', /no open positions/i.test(positions) ? 'No open positions' : 'Exposure available');

    if (/loading/i.test(orders)) setStatus('execution', '', 'Loading orders');
    else if (/timed out|failed/i.test(orders)) setStatus('execution', 'error', 'Order feed unavailable');
    else setStatus('execution', 'ok', /no orders/i.test(orders) ? 'No recent orders' : 'Execution feed available');

    if (/loading/i.test(signals)) setStatus('signals', '', 'Loading AI signals');
    else if (/timed out|failed/i.test(signals)) setStatus('signals', 'error', 'Signal feed unavailable');
    else setStatus('signals', 'ok', /no recent/i.test(signals) ? 'No recent signals' : 'AI signal feed available');
  }

  function boot() {
    const sync = $('[data-dashboard-sync]');
    if (sync) sync.textContent = `Updated ${new Date().toLocaleTimeString()}`;
    inspect();
    window.setInterval(inspect, 1500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
