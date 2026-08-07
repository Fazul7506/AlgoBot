export const deploymentModule = { init() { document.dispatchEvent(new CustomEvent("automation:deployment:ready")); } };
