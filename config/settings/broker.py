"""Broker and third-party provider settings. All deployment-specific values come from the environment."""

from .utils import env, env_bool

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", "")
DERIV_OAUTH_CLIENT_ID = env("DERIV_OAUTH_CLIENT_ID", env("BROKER_OAUTH_CLIENT_ID", ""))
DERIV_APP_ID = env("DERIV_APP_ID", env("BROKER_APP_ID", DERIV_OAUTH_CLIENT_ID))
DERIV_REDIRECT_URI = env("DERIV_REDIRECT_URI", env("BROKER_REDIRECT_URI", ""))
DERIV_API_BASE_URL = env("DERIV_API_BASE_URL", "https://api.derivws.com").rstrip("/")
DERIV_OPTIONS_ACCOUNTS_URL = env("DERIV_OPTIONS_ACCOUNTS_URL", f"{DERIV_API_BASE_URL}/trading/v1/options/accounts").rstrip("/")
DERIV_PUBLIC_WS_URL = env("DERIV_PUBLIC_WS_URL", "wss://api.derivws.com/trading/v1/options/ws/public")
DERIV_AUTH_WS_BASE_URL = env("DERIV_AUTH_WS_BASE_URL", DERIV_PUBLIC_WS_URL)

# Account selection is a control-plane operation. Keep the switch configurable
# while leaving live trading and broker connectivity independently gated.
ENABLE_BROKER_ACCOUNT_SWITCH = env_bool("ENABLE_BROKER_ACCOUNT_SWITCH", True)

BROKER_APP_ID = env("BROKER_APP_ID", DERIV_APP_ID)
BROKER_WS_URL = env("BROKER_WS_URL", DERIV_PUBLIC_WS_URL)
BROKER_OAUTH_CLIENT_ID = env("BROKER_OAUTH_CLIENT_ID", DERIV_OAUTH_CLIENT_ID)
BROKER_REDIRECT_URI = env("BROKER_REDIRECT_URI", DERIV_REDIRECT_URI)
