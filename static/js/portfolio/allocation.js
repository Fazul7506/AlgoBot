export function initAllocationDashboard(payload = {}) {
  return { module: "allocation", payload, timestamp: new Date().toISOString() };
}
