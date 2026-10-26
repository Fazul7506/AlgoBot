from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.brokers.services import _queue_automation_event


class BrokerAutomationQueueFailureTests(SimpleTestCase):
    @override_settings(DJANGO_TESTING=False)
    @patch("apps.automation.tasks.process_event.apply")
    @patch("apps.automation.tasks.process_event.delay", side_effect=RuntimeError("broker unavailable"))
    def test_queue_failure_never_executes_automation_inline(self, delay, apply):
        account = SimpleNamespace(pk=42, user_id=7)

        with self.assertLogs("apps.brokers.services", level="WARNING") as captured:
            _queue_automation_event("BrokerConnected", account, {"broker_type": "deriv"})

        delay.assert_called_once_with("BrokerConnected", "broker", {"broker_type": "deriv"}, 7)
        apply.assert_not_called()
        self.assertTrue(captured.records[0].automation_event_dropped)
