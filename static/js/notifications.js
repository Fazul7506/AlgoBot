(function () {
  const eventName = "notifications:ready";
  window.AlgoBotMonitoring = window.AlgoBotMonitoring || { events: [] };
  window.AlgoBotMonitoring.events.push(eventName);
  document.dispatchEvent(new CustomEvent(eventName));
})();
