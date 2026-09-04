from django.contrib.auth.decorators import login_required
from django.http import Http404

from core.views_user_modules import (
    automation_workspace, bot_runtime_workspace,
    audit_workspace, security_workspace,
)


@login_required
def operations_center(request, module="automation"):
    """Route supported operational workspaces to their owning views."""
    handlers = {
        "automation": automation_workspace,
        "deployments": bot_runtime_workspace,
        "audit": audit_workspace,
        "security": security_workspace,
    }
    handler = handlers.get(module)
    if not handler:
        raise Http404("Unknown operations module.")
    return handler(request)
