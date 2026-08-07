export function initCashflowDashboard(payload = {}) {
  return { module: "cashflow", payload, timestamp: new Date().toISOString() };
}
