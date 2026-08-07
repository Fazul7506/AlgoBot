export function initAnalyticsDashboard(payload = {}) {
  return { module: "analytics", payload, timestamp: new Date().toISOString() };
}
