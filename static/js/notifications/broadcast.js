export const broadcastModule = { init() { document.dispatchEvent(new CustomEvent("notifications:broadcast:ready")); } };
