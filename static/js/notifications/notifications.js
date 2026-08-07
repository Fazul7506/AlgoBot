export const notificationsModule = { init() { document.dispatchEvent(new CustomEvent("notifications:notifications:ready")); } };
