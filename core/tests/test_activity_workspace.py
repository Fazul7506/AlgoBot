from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.observability.models import AuditEvent


class CanonicalActivityIsolationTests(TestCase):
    def test_retired_activity_workspace_is_not_routable(self):
        user = get_user_model().objects.create_user(username="activity-owner", password="test-password")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/operations/audit/").status_code, 404)

    def test_canonical_activity_feed_is_user_scoped(self):
        user = get_user_model().objects.create_user(username="activity-feed-owner", password="test-password")
        other = get_user_model().objects.create_user(username="activity-feed-other", password="test-password")
        own = AuditEvent.objects.create(actor_id=user.pk, action="order_submitted", resource_type="trading", resource_id="own-order")
        AuditEvent.objects.create(actor_id=other.pk, action="private_action", resource_type="security", resource_id="must-not-show")
        self.client.force_login(user)
        response = self.client.get("/api/observability/audit/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["events"][0]["id"], own.pk)
        self.assertNotContains(response, "must-not-show")

    def test_security_center_uses_the_single_activity_stream(self):
        user = get_user_model().objects.create_user(username="security-feed-owner", password="test-password")
        other = get_user_model().objects.create_user(username="security-feed-other", password="test-password")
        AuditEvent.objects.create(actor_id=user.pk, action="login_failed", resource_type="Authentication", outcome="failed")
        AuditEvent.objects.create(actor_id=other.pk, action="login_failed", resource_type="Authentication", outcome="failed")
        self.client.force_login(user)
        response = self.client.get("/operations/security/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "login_failed")
