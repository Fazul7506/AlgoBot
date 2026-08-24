from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.notifications.models import Notification, NotificationPreference


class NotificationCenterContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="notification-ui", password="password")

    def test_page_requires_authentication(self):
        response = self.client.get(reverse("notifications_page"))
        self.assertEqual(response.status_code, 302)

    def test_authenticated_page_has_broker_aware_center(self):
        self.client.force_login(self.user)
        NotificationPreference.objects.create(user=self.user, channel="in_app", enabled=True)
        Notification.objects.create(user=self.user, title="Broker event", message="Confirmed", category="broker", priority="success", status="delivered")
        response = self.client.get(reverse("notifications_page"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification Center")
        self.assertContains(response, "No fabricated client-side events")
        self.assertContains(response, "Broker connected")
