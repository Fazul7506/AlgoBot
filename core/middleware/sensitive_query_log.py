"""Redact authentication secrets from request and application log messages."""
import logging
import re

_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?i)([?&](?:code|state|token|id_token|access_token|refresh_token|"
    r"session|sessionid|nonce|code_verifier|assertion)=)[^&\s\"'<>]+"
)
_SENSITIVE_PATH_VALUE = re.compile(
    r"(?i)(/(?:reset-password|password-reset)/)[A-Za-z0-9_-]{20,}"
)


class SensitiveQueryLogFilter(logging.Filter):
    """Remove OAuth codes, state, verification tokens and session values from logs."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = _SENSITIVE_QUERY_VALUE.sub(r"\1[REDACTED]", message)
        redacted = _SENSITIVE_PATH_VALUE.sub(r"\1[REDACTED]", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True
