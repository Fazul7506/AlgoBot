export const preferencesModule = { init() { document.dispatchEvent(new CustomEvent("notifications:preferences:ready")); } };
