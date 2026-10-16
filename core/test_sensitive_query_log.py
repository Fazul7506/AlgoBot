"""Regression tests for redacting secrets from access-log query strings."""
import logging
from unittest import TestCase

from core.middleware.sensitive_query_log import SensitiveQueryLogFilter


class SensitiveQueryLogFilterTests(TestCase):
    def test_redacts_oauth_and_verification_secrets_but_keeps_safe_parameters(self):
        record = logging.LogRecord(
            name="daphne.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='"GET /auth/google/callback/?state=state-secret&code=oauth-secret&scope=email HTTP/1.1" 302',
            args=(),
            exc_info=None,
        )

        self.assertTrue(SensitiveQueryLogFilter().filter(record))
        message = record.getMessage()

        self.assertNotIn("state-secret", message)
        self.assertNotIn("oauth-secret", message)
        self.assertIn("state=[REDACTED]", message)
        self.assertIn("code=[REDACTED]", message)
        self.assertIn("scope=email", message)

    def test_redacts_verification_token_and_session_parameters(self):
        record = logging.LogRecord(
            name="django.server",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="/verify-email/?token=verification-secret&sessionid=session-secret",
            args=(),
            exc_info=None,
        )

        SensitiveQueryLogFilter().filter(record)
        message = record.getMessage()

        self.assertNotIn("verification-secret", message)
        self.assertNotIn("session-secret", message)
        self.assertIn("token=[REDACTED]", message)
        self.assertIn("sessionid=[REDACTED]", message)

    def test_redacts_password_reset_tokens_in_path(self):
        record = logging.LogRecord(
            name="daphne.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='GET /reset-password/verylongsecretresettokenvalue1234567890/ HTTP/1.1',
            args=(),
            exc_info=None,
        )

        SensitiveQueryLogFilter().filter(record)
        message = record.getMessage()

        self.assertNotIn("verylongsecretresettokenvalue1234567890", message)
        self.assertIn("/reset-password/[REDACTED]/", message)
