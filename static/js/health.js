(function () {
  const eventName = "health:ready";
  window.AlgoBotMonitoring = window.AlgoBotMonitoring || { events: [] };
  window.AlgoBotMonitoring.events.push(eventName);
  document.dispatchEvent(new CustomEvent(eventName));
})();
