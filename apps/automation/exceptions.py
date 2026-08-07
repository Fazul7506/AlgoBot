class AutomationError(Exception): pass
class WorkflowValidationError(AutomationError): pass
class ApprovalRequired(AutomationError): pass
class SecureExecutionError(AutomationError): pass
