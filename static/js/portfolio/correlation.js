export function initCorrelationDashboard(payload = {}) {
  return { module: "correlation", payload, timestamp: new Date().toISOString() };
}
