export function initBenchmarkDashboard(payload = {}) {
  return { module: "benchmark", payload, timestamp: new Date().toISOString() };
}
