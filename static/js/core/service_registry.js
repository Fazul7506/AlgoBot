/* AlgoBot global service registry. */
(function () {
  'use strict';
  if (window.AlgoBotServiceRegistry) return;
  var definitions = {
    dashboard: {paths: ['/dashboard/'], module: 'dashboard.js'},
    trading: {paths: ['/trading/'], module: 'trading_terminal.js'},
    'market-data': {paths: ['/markets/', '/market-scanner/'], module: 'market_watch.js'},
    orders: {paths: ['/orders/'], module: 'orders.js'},
    'trade-history': {paths: ['/trade-history/'], module: 'trade_history.js'},
    positions: {paths: ['/positions/'], module: 'positions.js'},
    signals: {paths: ['/signals/'], module: 'signals.js'},
    strategies: {paths: ['/strategies/'], module: 'strategy_builder.js'},
    backtesting: {paths: ['/backtesting/'], module: 'backtesting_workspace_fix.js'},
    predictions: {paths: ['/predictions/', '/analysis/'], module: 'predictions_workspace_fix.js'},
    ai: {paths: ['/analysis/'], module: 'ai_trading_ui.js'},
    risk: {paths: ['/risk/'], module: 'risk.js'},
    monitoring: {paths: ['/monitoring/'], module: 'monitoring_dashboard.js'},
    notifications: {paths: ['/notifications/'], module: 'notifications_center.js'},
    automation: {paths: ['/automation/'], module: 'automation_dashboard.js'},
    portfolio: {paths: ['/portfolio/'], module: 'portfolio_dashboard.js'},
    brokers: {paths: ['/operations/brokers/'], module: 'broker_accounts.js'},
    developer: {paths: ['/developer/'], module: 'developer_portal.js'},
    billing: {paths: ['/billing/'], module: null},
    operations: {paths: ['/operations/'], module: null}
  };
  var currentPath = function () { return (window.location.pathname.replace(/\/+$/, '/') || '/'); };
  var servicesForCurrentPage = function () {
    var path = currentPath();
    return Object.keys(definitions).filter(function (name) {
      return definitions[name].paths.some(function (prefix) { return path.indexOf(prefix) === 0; });
    });
  };
  var registerPageServices = function () {
    var facade = window.AlgoBotServices;
    var names = servicesForCurrentPage();
    names.forEach(function (name) {
      if (facade && typeof facade.register === 'function') {
        facade.register(name, {page: currentPath(), module: definitions[name].module});
      }
    });
    document.body.dataset.algobotServices = names.join(',');
    window.dispatchEvent(new CustomEvent('algobot:page-services-ready', {detail: {services: names, page: currentPath()}}));
    return names;
  };
  var diagnostics = function () {
    var runtime = window.AlgoBotServiceRuntime;
    return {page: currentPath(), services: servicesForCurrentPage(), runtime: runtime && typeof runtime.snapshot === 'function' ? runtime.snapshot() : null};
  };
  window.AlgoBotServiceRegistry = {
    definitions: definitions,
    current: servicesForCurrentPage,
    registerPageServices: registerPageServices,
    diagnostics: diagnostics
  };
  var boot = function () { registerPageServices(); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
