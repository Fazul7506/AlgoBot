export const alertsModule = { init() { document.dispatchEvent(new CustomEvent("notifications:alerts:ready")); } };
