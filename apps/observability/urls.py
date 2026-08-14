from django.urls import path
from . import views
urlpatterns = [
    path("dashboard/", views.dashboard, name="observability_dashboard_api"),
    path("health/", views.record_health, name="observability_health_api"),
    path("metrics/", views.record_metric, name="observability_metric_api"),
    path("events/", views.emit_event, name="observability_event_api"),
    path("audit/", views.audit, name="observability_audit_api"),
]
