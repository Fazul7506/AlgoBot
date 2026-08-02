from rest_framework.permissions import IsAuthenticatedOrReadOnly

class MonitoringPermission(IsAuthenticatedOrReadOnly):
    pass
class AlertPermission(IsAuthenticatedOrReadOnly):
    pass
class AuditLogPermission(IsAuthenticatedOrReadOnly):
    pass
