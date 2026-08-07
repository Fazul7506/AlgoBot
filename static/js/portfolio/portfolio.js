export function initPortfolioDashboard(payload = {}) {
  return { module: "portfolio", payload, timestamp: new Date().toISOString() };
}
