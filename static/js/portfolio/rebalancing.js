export function initRebalancingDashboard(payload = {}) {
  return { module: "rebalancing", payload, timestamp: new Date().toISOString() };
}
