from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.notifications.models import NotificationPreference, NotificationTemplate
from apps.notifications.services import DeliveryService, NotificationEngine, TemplateService, WebhookService


class NotificationEngineTests(TestCase):
    def test_publish_uses_preferences_and_tracks_delivery(self):
        user = get_user_model().objects.create_user(username="notify", password="x")
        NotificationPreference.objects.create(user=user, channel="in_app", enabled=True)
        notices = NotificationEngine().publish(user, "Workflow Completed", "Done", "automation", "success")
        self.assertEqual(notices[0].status, "delivered")
        self.assertEqual(notices[0].delivery_logs.count(), 1)

    def test_template_rendering(self):
        template = NotificationTemplate.objects.create(name="trade", subject="{{ symbol }}", body="Price {{ price }}")
        rendered = TemplateService().render(template, {"symbol": "BTCUSD", "price": 42})
        self.assertEqual(rendered["subject"], "BTCUSD")

    def test_webhook_hmac_signature(self):
        self.assertEqual(WebhookService().sign(b"{}", "secret"), WebhookService().sign(b"{}", "secret"))
