"""Email and outbound communication settings."""

from .utils import env

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@algobot.dpdns.org")
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = env("EMAIL_PORT", "")
EMAIL_HOST_USER = env("EMAIL_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD", "")
BREVO_API_KEY = env("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL", DEFAULT_FROM_EMAIL)

# Verified Brevo senders used by AlgoBot's transactional email policy.
ALGOBOT_SECURITY_EMAIL = env("ALGOBOT_SECURITY_EMAIL", "security@algobot.dpdns.org")
ALGOBOT_SUPPORT_EMAIL = env("ALGOBOT_SUPPORT_EMAIL", "support@algobot.dpdns.org")
ALGOBOT_NOREPLY_EMAIL = env("ALGOBOT_NOREPLY_EMAIL", "noreply@algobot.dpdns.org")
