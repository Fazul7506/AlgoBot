export const schedulerModule = { init() { document.dispatchEvent(new CustomEvent("automation:scheduler:ready")); } };
