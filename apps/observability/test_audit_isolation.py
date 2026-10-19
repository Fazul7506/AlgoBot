from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.monitoring.models import AuditLog as StructuredAuditLog
from apps.observability.models import AuditEvent
from core.middleware.audit_middleware import AuditMiddleware


class AuditApiIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="audit-api-owner", password="test-password")
        self.other = User.objects.create_user(username="audit-api-other", password="test-password")
        self.own_event = AuditEvent.objects.create(
            actor_id=self.user.pk, action="order_submitted", resource_type="execution",
            resource_id="order-123", outcome="success", metadata={"token": "must-not-leak"},
        )
        self.foreign_event = AuditEvent.objects.create(
            actor_id=self.other.pk, action="credential_rotated", resource_type="security",
            resource_id="foreign-secret", outcome="success",
        )

    def test_audit_api_is_scoped_and_does_not_return_raw_metadata(self):
        self.client.force_login(self.user)
        response = self.client.get("/api/observability/audit/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["events"][0]["id"], self.own_event.pk)
        self.assertNotIn("foreign-secret", response.content.decode())
        self.assertNotIn("must-not-leak", response.content.decode())
        self.assertNotIn("metadata", payload["events"][0])

    def test_audit_api_filters_and_caps_page_size(self):
        AuditEvent.objects.create(
            actor_id=self.user.pk, action="order_rejected", resource_type="execution",
            resource_id="order-456", outcome="failed",
        )
        self.client.force_login(self.user)
        response = self.client.get("/api/observability/audit/?action=order&page_size=1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pagination"]["total"], 2)
        self.assertEqual(payload["pagination"]["page_size"], 1)
        self.assertEqual(len(payload["events"]), 1)

    def test_dashboard_merges_user_request_and_application_audit_streams(self):
        StructuredAuditLog.objects.create(
            user=self.user, action="post_completed", module="execution",
            resource="/api/orders/submit/ | status=201 | request_id=abc123",
        )
        self.client.force_login(self.user)
        response = self.client.get("/api/observability/dashboard/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        actions = {item["action"] for item in payload["audit"]}
        self.assertIn("post_completed", actions)
        self.assertIn("order_submitted", actions)
        self.assertNotIn("credential_rotated", actions)

    def test_mutating_request_is_recorded_without_storing_request_body(self):
        factory = RequestFactory()
        request = factory.post("/api/orders/submit/", data='{"token":"do-not-store"}', content_type="application/json")
        request.user = self.user
        middleware = AuditMiddleware(lambda req: HttpResponse("ok", status=201))
        middleware.process_request(request)
        response = middleware.process_response(request, HttpResponse("ok", status=201))
        record = StructuredAuditLog.objects.get(user=self.user, action="post_completed")
        self.assertEqual(record.module, "execution")
        self.assertIn("/api/orders/submit/", record.resource)
        self.assertIn("request_id=", record.resource)
        self.assertEqual(response["X-Request-ID"], request.algobot_request_id)
        self.assertFalse(record.new_value)
        from core.models import AuditLog as RequestAuditLog
        request_record = RequestAuditLog.objects.filter(user=self.user, path="/api/orders/submit/").latest("created_at")
        self.assertEqual(request_record.request_body, "")
        self.assertEqual(request_record.response_body, "")
