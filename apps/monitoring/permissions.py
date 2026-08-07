from rest_framework.permissions import IsAuthenticated

class MonitoringPermission(IsAuthenticated):
    pass
class AlertPermission(IsAuthenticated):
    pass
class AuditLogPermission(IsAuthenticated):
    pass
