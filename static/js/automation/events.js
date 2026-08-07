export const eventsModule = { init() { document.dispatchEvent(new CustomEvent("automation:events:ready")); } };
