/* AlgoBot global service registry. Page modules register capabilities here;
 * shared transport/account/lifecycle code remains in core/algobot_services.js. */
(() => {
  'use strict';
  if (window.AlgoBotServiceRegistry) return;
  const definitions = Object.freeze({
    dashboard: { paths: ['/dashboard/'], module: 'dashboard.js' },
    trading: { paths: ['/trading/'], module: 'trading_terminal.js' },
    market-data: { paths: ['/markets/', '/market-scanner/'], module: 'market_watch.js' },
    orders: { paths: ['/orders/'], module: 'orders.js' },
    trade-history: { paths: ['/trade-history/'], module: 'trade_history.js' },
    positions: { paths: ['/positions/'], module: 'positions.js' },
    signals: { paths: ['/signals/'], module: 'signals.js' },
    strategies: { paths: ['/strategies/'], module: 'strategy_builder.js' },
    backtesting: { paths: ['/backtesting/'], module: 'backtesting_workspace_fix.js' },
    predictions: { paths: ['/predictions/', '/analysis/'], module: 'predictions_workspace_fix.js' },
    ai: { paths: ['/analysis/'], module: 'ai_trading_ui.js' },
    risk: { paths: ['/risk/'], module: 'risk.js' },
    monitoring: { paths: ['/monitoring/'], module: 'monitoring_dashboard.js' },
    notifications: { paths: ['/notifications/'], module: 'notifications_center.js' },
    automation: { paths: ['/automation/'], module: 'automation_dashboard.js' },
    portfolio: { paths: ['/portfolio/'], module: 'portfolio_dashboard.js' },
    brokers: { paths: ['/operations/brokers/'], module: 'broker_accounts.js' },
    developer: { paths: ['/developer/'], module: 'developer_portal.js' },
    billing: { paths: ['/billing/'], module: null },
    operations: { paths: ['/operations/'], module: null }
  });
  const currentPath = () => window.location.pathname.replace(/\/+$/, '/') || '/';
  const servicesForCurrentPage = () => Object.entries(definitions).filter(([, value]) => value.paths.some(path => currentPath().startsWith(path))).map(([name]) => name);
  const registerPageServices = () => {
    const facade = window.AlgoBotServices;
    const names = servicesForCurrentPage();
    names.forEach(name => facade?.register(name, { page: currentPath(), module: definitions[name].module }));
    document.body.dataset.algobotServices = names.join(',');
    window.dispatchEvent(new CustomEvent('algobot:page-services-ready', { detail: { services: names, page: currentPath() } }));
    return names;
  };
  const diagnostics = () => ({ page: currentPath(), services: servicesForCurrentPage(), runtime: window.AlgoBotServiceRuntime?.snapshot?.() || null });
  window.AlgoBotServiceRegistry = Object.freeze({ definitions, current: servicesForCurrentPage, registerPageServices, diagnostics });
  const boot = () => registerPageServices();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();
