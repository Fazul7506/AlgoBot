"""Security settings for AlgoBot."""

from .utils import env, env_bool

SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)

SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", "Lax")

# Optional shared-cookie domain for the split UI/API deployment:
# algobot.dpdns.org (browser UI) -> api.algobot.dpdns.org (DNS-only API).
# Leave unset for single-origin/local deployments.
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN", "") or None
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN", "") or None

CREDENTIALS_ENCRYPTION_KEY = env("CREDENTIALS_ENCRYPTION_KEY", "")
AUDIT_LOG_ENABLED = env_bool("AUDIT_LOG_ENABLED", True)
TWO_FACTOR_ENABLED = env_bool("TWO_FACTOR_ENABLED", True)
TWO_FACTOR_ISSUER = env("TWO_FACTOR_ISSUER", "DerivBot")

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
