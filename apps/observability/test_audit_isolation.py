from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.observability.models import AuditEvent
from core.middleware.activity_middleware import ActivityMiddleware


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

    def test_dashboard_reads_request_and_application_activity_from_one_stream(self):
        AuditEvent.objects.create(
            actor_id=self.user.pk, action="post_completed", resource_type="execution",
            resource_id="/api/orders/submit/ | status=201 | request_id=abc123",
            request_path="/api/orders/submit/", http_method="POST", http_status=201,
            module="execution", resource="/api/orders/submit/",
        )
        self.client.force_login(self.user)
        response = self.client.get("/api/observability/dashboard/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        actions = {item["action"] for item in payload["audit"]}
        self.assertIn("post_completed", actions)
        self.assertIn("order_submitted", actions)
        self.assertNotIn("credential_rotated", actions)
        self.assertEqual(len([item for item in payload["audit"] if item["action"] == "post_completed"]), 1)

    def test_browser_token_unauthenticated_response_is_not_bridged_as_a_flash_message(self):
        from unittest.mock import patch
        from django.http import JsonResponse

        request = RequestFactory().get("/api/auth/browser-token/")
        response = JsonResponse(
            {"detail": "Authentication credentials were not provided.", "code": "not_authenticated"},
            status=401,
        )
        with patch("core.middleware.activity_middleware.messages.add_message") as add_message:
            ActivityMiddleware._bridge_message(request, response)
        add_message.assert_not_called()

    def test_mutating_request_is_recorded_without_storing_request_body(self):
        factory = RequestFactory()
        request = factory.post("/api/orders/submit/", data='{"token":"do-not-store"}', content_type="application/json")
        request.user = self.user
        middleware = ActivityMiddleware(lambda req: HttpResponse("ok", status=201))
        middleware.process_request(request)
        response = middleware.process_response(request, HttpResponse("ok", status=201))
        record = AuditEvent.objects.get(actor_id=self.user.pk, action="post_completed", request_path="/api/orders/submit/")
        self.assertEqual(record.module, "execution")
        self.assertIn("/api/orders/submit/", record.resource)
        self.assertIn("request_id=", record.resource_id)
        self.assertEqual(record.http_method, "POST")
        self.assertEqual(record.http_status, 201)
        self.assertEqual(response["X-Request-ID"], request.algobot_request_id)
        self.assertFalse(record.new_value)
        self.assertNotIn("do-not-store", str(record.metadata))
