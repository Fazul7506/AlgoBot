from .services import WorkflowDesignerService
def validate_workflow_definition(definition): return WorkflowDesignerService().validate(definition)
