from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.monitoring.models import Alert, AuditLog, Incident, LogEntry, Metric, SystemHealth, TraceSpan


class MonitoringApiIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="monitoring-owner", password="test-password")
        self.other = User.objects.create_user(username="monitoring-other", password="test-password")
        self.own_alert = Alert.objects.create(
            user=self.user, title="Own alert", category="trading", severity="warning",
            message="Own alert message", source="test",
        )
        self.foreign_alert = Alert.objects.create(
            user=self.other, title="Foreign alert", category="security", severity="critical",
            message="Foreign account data", source="test",
        )
        AuditLog.objects.create(user=self.other, action="secret_action", module="security", resource="sensitive-resource")
        LogEntry.objects.create(stream="application", level="ERROR", message="private token diagnostic", context={"token": "do-not-expose"})
        Metric.objects.create(metric_name="private_metric", value=1, module="test", tags={"user": self.other.pk})
        TraceSpan.objects.create(trace_id="private-trace", span_id="private-span", operation="private-operation", module="security", attributes={"secret": "private"})
        SystemHealth.objects.create(service_name="Database", status="healthy", details={"host": "private-internal-host"})

    def test_global_operational_telemetry_requires_staff(self):
        self.client.force_login(self.user)
        for path in (
            "/api/monitoring/health/",
            "/api/monitoring/broker/",
            "/api/monitoring/infrastructure/",
            "/api/monitoring/metrics/",
            "/api/monitoring/audit/",
            "/api/monitoring/logs/",
            "/api/monitoring/traces/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_user_alerts_and_acknowledgement_are_tenant_scoped(self):
        self.client.force_login(self.user)
        listing = self.client.get("/api/monitoring/alerts/")
        self.assertEqual(listing.status_code, 200)
        body = listing.content.decode("utf-8")
        self.assertIn("Own alert", body)
        self.assertNotIn("Foreign alert", body)
        denied = self.client.post(
            "/api/monitoring/alerts/acknowledge/",
            data={"id": self.foreign_alert.pk},
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 404)
        self.foreign_alert.refresh_from_db()
        self.assertFalse(self.foreign_alert.acknowledged)

    def test_incidents_are_scoped_to_assignee_or_owned_alert(self):
        foreign_incident = Incident.objects.create(
            title="Foreign incident", severity="critical", alert=self.foreign_alert, assigned_to=self.other
        )
        own_incident = Incident.objects.create(
            title="Own incident", severity="warning", alert=self.own_alert, assigned_to=self.user
        )
        self.client.force_login(self.user)
        response = self.client.get("/api/monitoring/incidents/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Own incident", body)
        self.assertNotIn("Foreign incident", body)
