from django.test import TestCase
from apps.monitoring.models import Alert, AuditLog, Metric
from apps.monitoring.services import AlertEngine, AuditService, MetricsService, SelfHealingService

class MonitoringServiceTests(TestCase):
    def test_alert_engine_creates_threshold_alerts(self):
        alerts = AlertEngine().evaluate({"cpu": 95})
        self.assertEqual(len(alerts), 1)
        self.assertEqual(Alert.objects.count(), 1)

    def test_metrics_service_records_metric(self):
        metric = MetricsService().record("latency", 12.5, "ms", "api")
        self.assertEqual(metric.unit, "ms")
        self.assertEqual(Metric.objects.count(), 1)

    def test_audit_service_hashes_records(self):
        log = AuditService().record("login", "authentication", resource="session")
        self.assertTrue(log.hash)
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_self_healing_rejects_unknown_action(self):
        result = SelfHealingService().execute("unknown", "monitoring")
        self.assertEqual(result["status"], "rejected")
