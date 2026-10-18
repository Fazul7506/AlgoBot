"""Email and outbound communication settings."""

from .utils import env

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@algobot.dpdns.org")
EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
BREVO_API_KEY = env("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL", DEFAULT_FROM_EMAIL)

# Category-specific sender overrides are optional. By default, use the
# configured Brevo sender so every transactional category uses a verified
# sender address unless an operator explicitly configures separate senders.
ALGOBOT_SECURITY_EMAIL = env("ALGOBOT_SECURITY_EMAIL", BREVO_SENDER_EMAIL)
ALGOBOT_SUPPORT_EMAIL = env("ALGOBOT_SUPPORT_EMAIL", BREVO_SENDER_EMAIL)
ALGOBOT_NOREPLY_EMAIL = env("ALGOBOT_NOREPLY_EMAIL", BREVO_SENDER_EMAIL)
