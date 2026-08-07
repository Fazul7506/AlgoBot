export const triggersModule = { init() { document.dispatchEvent(new CustomEvent("automation:triggers:ready")); } };
