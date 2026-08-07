export function initForecastingDashboard(payload = {}) {
  return { module: "forecasting", payload, timestamp: new Date().toISOString() };
}
