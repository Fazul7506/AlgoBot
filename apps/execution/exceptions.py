class ExecutionError(Exception): pass
class OrderValidationError(ExecutionError): pass
class NonRetryableExecutionError(ExecutionError): pass
class RetryableExecutionError(ExecutionError): pass
class PermissionDeniedExecutionError(ExecutionError): pass
