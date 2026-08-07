export const deliveryModule = { init() { document.dispatchEvent(new CustomEvent("notifications:delivery:ready")); } };
