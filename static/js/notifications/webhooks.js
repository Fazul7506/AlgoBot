export const webhooksModule = { init() { document.dispatchEvent(new CustomEvent("notifications:webhooks:ready")); } };
