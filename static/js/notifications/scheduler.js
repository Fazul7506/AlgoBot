export const schedulerModule = { init() { document.dispatchEvent(new CustomEvent("notifications:scheduler:ready")); } };
