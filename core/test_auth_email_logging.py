from unittest.mock import patch

from django.test import SimpleTestCase

from core.browser_auth import _send_account_email


class AuthenticationEmailLoggingTests(SimpleTestCase):
    @patch(
        "apps.notifications.services.send_transactional_email",
        side_effect=RuntimeError("private recipient and provider response must not be logged"),
    )
    def test_email_provider_failure_logs_only_exception_type(self, _send_email):
        with self.assertLogs("account_auth", level="ERROR") as captured:
            result = _send_account_email(
                "Verify account",
                "private verification URL token=secret",
                "person@example.test",
            )

        self.assertFalse(result)
        output = "\n".join(captured.output)
        self.assertIn("error_type=RuntimeError", output)
        self.assertNotIn("private recipient", output)
        self.assertNotIn("person@example.test", output)
        self.assertNotIn("secret", output)
        self.assertNotIn("Traceback", output)
