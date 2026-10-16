"""Email and outbound communication settings."""

from .utils import env, env_bool

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@algobot.dpdns.org")
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = env("EMAIL_PORT", "")
EMAIL_HOST_USER = env("EMAIL_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD", "")
# SMTP commonly uses STARTTLS on 587 or implicit TLS on 465. Honor explicit
# overrides while choosing the secure default from the configured port.
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", EMAIL_PORT == "465")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", bool(EMAIL_PORT and EMAIL_PORT != "465"))
if EMAIL_USE_SSL and EMAIL_USE_TLS:
    raise RuntimeError("EMAIL_USE_SSL and EMAIL_USE_TLS cannot both be enabled.")
BREVO_API_KEY = env("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL", DEFAULT_FROM_EMAIL)

# Category-specific sender overrides are optional. By default, use the
# configured Brevo sender so every transactional category uses a verified
# sender address unless an operator explicitly configures separate senders.
ALGOBOT_SECURITY_EMAIL = env("ALGOBOT_SECURITY_EMAIL", BREVO_SENDER_EMAIL)
ALGOBOT_SUPPORT_EMAIL = env("ALGOBOT_SUPPORT_EMAIL", BREVO_SENDER_EMAIL)
ALGOBOT_NOREPLY_EMAIL = env("ALGOBOT_NOREPLY_EMAIL", BREVO_SENDER_EMAIL)
