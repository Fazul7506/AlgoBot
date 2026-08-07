export const approvalsModule = { init() { document.dispatchEvent(new CustomEvent("automation:approvals:ready")); } };
