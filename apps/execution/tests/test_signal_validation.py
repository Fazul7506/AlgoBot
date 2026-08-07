from django.test import SimpleTestCase
from apps.execution.signal_validation import SignalValidationService


class SignalValidationServiceTests(SimpleTestCase):
    def test_returns_structured_validation_errors(self):
        result = SignalValidationService().validate(signal={}, trading_enabled=False, websocket_connected=False)
        self.assertFalse(result.is_valid)
        self.assertIn("Trading is disabled", result.errors)
        self.assertIn("Websocket is not connected", result.errors)
