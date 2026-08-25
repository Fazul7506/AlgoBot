"""Broker and third-party provider settings. All deployment-specific values come from the environment."""

from .utils import env

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", "")
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", "intasend").lower()
PAYMENT_HTTP_TIMEOUT = int(env("PAYMENT_HTTP_TIMEOUT", "20"))

INTASEND_PUBLIC_KEY = env("INTASEND_PUBLIC_KEY", "")
INTASEND_SECRET_KEY = env("INTASEND_SECRET_KEY", "")
INTASEND_WEBHOOK_CHALLENGE = env("INTASEND_WEBHOOK_CHALLENGE", "")
INTASEND_API_BASE_URL = env("INTASEND_API_BASE_URL", "https://api.intasend.com").rstrip("/")

PESAPAL_CONSUMER_KEY = env("PESAPAL_CONSUMER_KEY", "")
PESAPAL_CONSUMER_SECRET = env("PESAPAL_CONSUMER_SECRET", "")
PESAPAL_NOTIFICATION_ID = env("PESAPAL_NOTIFICATION_ID", "")
PESAPAL_API_BASE_URL = env("PESAPAL_API_BASE_URL", "https://pay.pesapal.com/v3").rstrip("/")

# Deriv OAuth / current Options API configuration.
# These names are defined here because production.py imports broker settings
# before validating the deployment configuration.
DERIV_OAUTH_CLIENT_ID = env("DERIV_OAUTH_CLIENT_ID", "")
DERIV_OAUTH_CLIENT_SECRET = env("DERIV_OAUTH_CLIENT_SECRET", "")
DERIV_OAUTH_SCOPE = env("DERIV_OAUTH_SCOPE", "trade")
DERIV_APP_ID = env("DERIV_APP_ID", "")
DERIV_LEGACY_APP_ID = env("DERIV_LEGACY_APP_ID", "")
DERIV_ENABLE_LEGACY_APP_ROUTING = env("DERIV_ENABLE_LEGACY_APP_ROUTING", "false").lower() in {"1", "true", "yes", "on"}
DERIV_API_TOKEN = env("DERIV_API_TOKEN", "")
DERIV_API_BASE_URL = env("DERIV_API_BASE_URL", "https://api.derivws.com").rstrip("/")
DERIV_OPTIONS_ACCOUNTS_URL = env(
    "DERIV_OPTIONS_ACCOUNTS_URL",
    f"{DERIV_API_BASE_URL}/trading/v1/options/accounts",
).rstrip("/")
DERIV_PUBLIC_WS_URL = env(
    "DERIV_PUBLIC_WS_URL",
    "wss://api.derivws.com/trading/v1/options/ws/public",
)
DERIV_AUTH_WS_BASE_URL = env(
    "DERIV_AUTH_WS_BASE_URL",
    "wss://api.derivws.com/trading/v1/options/ws",
).rstrip("/")
DERIV_REDIRECT_URI = env("DERIV_REDIRECT_URI", "")
ALLOW_LIVE_TRADING = env("ALLOW_LIVE_TRADING", "false").lower() in {"1", "true", "yes", "on"}
ENABLE_BROKER_ACCOUNT_SWITCH = env("ENABLE_BROKER_ACCOUNT_SWITCH", "false").lower() in {"1", "true", "yes", "on"}

# Generic broker aliases.
BROKER_APP_ID = env("BROKER_APP_ID", DERIV_APP_ID or DERIV_OAUTH_CLIENT_ID)
BROKER_WS_URL = env("BROKER_WS_URL", DERIV_PUBLIC_WS_URL)
BROKER_OAUTH_CLIENT_ID = env("BROKER_OAUTH_CLIENT_ID", DERIV_OAUTH_CLIENT_ID or BROKER_APP_ID)
BROKER_REDIRECT_URI = env("BROKER_REDIRECT_URI", DERIV_REDIRECT_URI)
