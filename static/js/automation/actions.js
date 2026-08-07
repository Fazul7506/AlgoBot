export const actionsModule = { init() { document.dispatchEvent(new CustomEvent("automation:actions:ready")); } };
