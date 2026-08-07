export const trackingModule = { init() { document.dispatchEvent(new CustomEvent("notifications:tracking:ready")); } };
