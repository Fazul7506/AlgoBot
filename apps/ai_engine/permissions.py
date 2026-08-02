from rest_framework.permissions import BasePermission, IsAuthenticated
class CanDeployAIModel(BasePermission):
    def has_permission(self, request, view): return bool(request.user and request.user.is_staff)
