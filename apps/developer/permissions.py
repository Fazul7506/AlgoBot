from rest_framework.permissions import BasePermission


class HasDeveloperScope(BasePermission):
    required_scope = "read"
    message = "This API key does not have the required developer scope."

    def has_permission(self, request, view):
        auth = getattr(request, "auth", None)
        if not auth:
            return bool(getattr(request.user, "is_authenticated", False))
        permissions = getattr(auth, "permissions", [])
        return self.required_scope in permissions or "admin" in permissions


class HasDeveloperAdminScope(HasDeveloperScope):
    required_scope = "admin"


class HasWebhookScope(HasDeveloperScope):
    required_scope = "webhooks"


class HasAnalyticsScope(HasDeveloperScope):
    required_scope = "analytics"
