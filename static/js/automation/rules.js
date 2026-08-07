export const rulesModule = { init() { document.dispatchEvent(new CustomEvent("automation:rules:ready")); } };
