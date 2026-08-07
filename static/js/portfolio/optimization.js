export function initOptimizationDashboard(payload = {}) {
  return { module: "optimization", payload, timestamp: new Date().toISOString() };
}
