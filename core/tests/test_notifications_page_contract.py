from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
        self.assertContains(response, "Checking broker")

class TopbarNotificationActionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="topbar-notification-user", password="password")
        self.other = get_user_model().objects.create_user(username="other-notification-user", password="password")
        self.client.force_login(self.user)

    def test_notification_api_feed_and_unread_count_only_include_in_app_deliveries(self):
        self.client.force_login(self.user)
        in_app = Notification.objects.create(
            user=self.user, title="Sign-in completed", message="Successful sign-in",
            channel="in_app", status="delivered",
        )
        Notification.objects.create(
            user=self.user, title="Sign-in completed", message="Successful sign-in",
            channel="gmail", status="sent",
        )
        response = self.client.get(reverse("enterprise-notifications-list"))
        self.assertEqual(response.status_code, 200)
        rows = response.json().get("results", response.json())
        self.assertEqual([row["id"] for row in rows], [in_app.pk])
        unread = self.client.get(reverse("enterprise-notifications-unread-count"))
        self.assertEqual(unread.json()["unread_count"], 1)

    def test_mark_all_read_only_marks_in_app_delivery_rows(self):
        self.client.force_login(self.user)
        in_app = Notification.objects.create(
            user=self.user, title="In-app", message="Visible", channel="in_app"
        )
        email = Notification.objects.create(
            user=self.user, title="Email", message="External channel", channel="gmail"
        )
        response = self.client.post(reverse("enterprise-notifications-mark-all-read"))
        self.assertEqual(response.status_code, 200)
        in_app.refresh_from_db()
        email.refresh_from_db()
        self.assertIsNotNone(in_app.read_at)
        self.assertIsNone(email.read_at)

    def test_mark_read_only_updates_the_authenticated_users_notification(self):
        notice = Notification.objects.create(user=self.user, title="Private alert", message="Only for this user")
        response = self.client.post(reverse("enterprise-notifications-mark-read", args=[notice.pk]))
        self.assertEqual(response.status_code, 200)
        notice.refresh_from_db()
        self.assertIsNotNone(notice.read_at)
        self.assertEqual(response.json()["id"], notice.pk)

    def test_mark_read_cannot_touch_another_users_notification(self):
        notice = Notification.objects.create(user=self.other, title="Private alert", message="Other user")
        response = self.client.post(reverse("enterprise-notifications-mark-read", args=[notice.pk]))
        self.assertEqual(response.status_code, 404)
        notice.refresh_from_db()
        self.assertIsNone(notice.read_at)

    def test_unread_count_is_scoped_to_authenticated_user(self):
        Notification.objects.create(user=self.user, title="Unread", message="Mine")
        Notification.objects.create(user=self.other, title="Other", message="Not mine")
        response = self.client.get(reverse("enterprise-notifications-unread-count"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 1)

    def test_mark_all_read_is_scoped_to_current_user(self):
        mine = Notification.objects.create(user=self.user, title="Mine", message="My alert")
        theirs = Notification.objects.create(user=self.other, title="Theirs", message="Other alert")
        response = self.client.post(reverse("enterprise-notifications-mark-all-read"))
        self.assertEqual(response.status_code, 200)
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertIsNotNone(mine.read_at)
        self.assertIsNone(theirs.read_at)
        self.assertGreaterEqual(response.json()["marked_read"], 1)
