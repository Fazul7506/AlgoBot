export function initReportsDashboard(payload = {}) {
  return { module: "reports", payload, timestamp: new Date().toISOString() };
}
