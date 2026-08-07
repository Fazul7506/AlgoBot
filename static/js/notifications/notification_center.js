export const notificationcenterModule = { init() { document.dispatchEvent(new CustomEvent("notifications:notification_center:ready")); } };
