export const recoveryModule = { init() { document.dispatchEvent(new CustomEvent("automation:recovery:ready")); } };
