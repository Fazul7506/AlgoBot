from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.monitoring.models import AuditLog


class AuditLogWorkspaceIsolationTests(TestCase):
    def test_activity_history_is_scoped_to_authenticated_user(self):
        user = get_user_model().objects.create_user(username="audit-owner", password="test-password")
        other = get_user_model().objects.create_user(username="audit-other", password="test-password")
        own_event = AuditLog.objects.create(
            user=user, action="order_viewed", module="trading", resource="order:own"
        )
        AuditLog.objects.create(
            user=other, action="credential_changed", module="security", resource="other-user"
        )
        self.client.force_login(user)
        response = self.client.get("/operations/audit/")
        self.assertEqual(response.status_code, 200)
        events = list(response.context["events"])
        self.assertEqual([event.pk for event in events], [own_event.pk])
        self.assertEqual(response.context["event_count"], 1)
        self.assertContains(response, "order:own")
        self.assertNotContains(response, "other-user")

    def test_activity_history_merges_application_events_without_leaking_other_users(self):
        from apps.observability.models import AuditEvent

        user = get_user_model().objects.create_user(username="audit-merge-owner", password="test-password")
        other = get_user_model().objects.create_user(username="audit-merge-other", password="test-password")
        own_request = AuditLog.objects.create(
            user=user, action="order_submitted", module="execution", resource="/api/orders/",
        )
        AuditEvent.objects.create(
            actor_id=user.pk, action="broker_order_acknowledged", resource_type="brokers",
            resource_id="account-123", outcome="success",
        )
        AuditEvent.objects.create(
            actor_id=other.pk, action="private_action", resource_type="security",
            resource_id="must-not-show", outcome="success",
        )
        self.client.force_login(user)
        response = self.client.get("/operations/audit/")
        self.assertEqual(response.status_code, 200)
        events = list(response.context["events"])
        self.assertEqual({event.action for event in events}, {"order_submitted", "broker_order_acknowledged"})
        self.assertIn(own_request.pk, {event.pk for event in events})
        self.assertNotContains(response, "must-not-show")
