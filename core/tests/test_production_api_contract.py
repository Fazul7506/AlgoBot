"""Regression checks for production browser/API authentication contracts."""
from pathlib import Path
from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class ProductionApiContractTests(SimpleTestCase):
    def test_account_switch_uses_jwt_and_keeps_session_on_token_refresh_retry(self):
        source = (ROOT / "static/js/core/frontend_data_contract.js").read_text(encoding="utf-8")
        self.assertIn("retryHeaders.set('Authorization','Bearer '+retryToken)", source)
        self.assertIn("const isSessionAccountSelectUrl=url=>", source)
        self.assertIn("const isSessionAccountContextUrl=url=>", source)
        self.assertIn("const sessionAccountContext=isSessionAccountContextUrl(url);", source)
        self.assertIn("credentials:sessionAccountContext?'include':'omit'", source)
        self.assertIn("const requestInit={credentials:sessionAccountContext?'include':'omit',...options,headers,cache:'no-store',signal:controller.signal};", source)
        self.assertIn("credentials:sessionAccountContext?'include':'omit',...options,headers:retryHeaders", source)
        self.assertNotIn("CSRF_TOKEN_UNAVAILABLE", source)
        self.assertNotIn("headers.set('X-CSRFToken',csrfToken)", source)
        self.assertNotIn("is_preferred", source)
        self.assertNotIn("is_default", source)

    def test_deriv_oauth_client_id_is_not_compared_to_numeric_app_id(self):
        source = (ROOT / "config/settings/production.py").read_text(encoding="utf-8")
        self.assertNotIn("DERIV_APP_ID != DERIV_OAUTH_CLIENT_ID", source)
        self.assertIn('"DERIV_OAUTH_CLIENT_ID": DERIV_OAUTH_CLIENT_ID', source)
        self.assertIn('"DERIV_APP_ID": DERIV_APP_ID', source)

    def test_deriv_app_id_never_defaults_to_oauth_client_id(self):
        source = (ROOT / "config/settings/broker.py").read_text(encoding="utf-8")
        self.assertIn('DERIV_APP_ID = env("DERIV_APP_ID", env("BROKER_APP_ID", ""))', source)
        self.assertNotIn('env("BROKER_APP_ID", DERIV_OAUTH_CLIENT_ID)', source)
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for legacy_name in ("BROKER_APP_ID=", "BROKER_WS_URL=", "BROKER_OAUTH_CLIENT_ID=", "BROKER_REDIRECT_URI=", "DJANGO_SECRET_KEY=", "DJANGO_DEBUG="):
            self.assertNotIn(legacy_name, example)
        self.assertNotIn("CELERY_BROKER_URL=", example)
        self.assertNotIn("CELERY_RESULT_BACKEND=", example)

    def test_optional_deriv_and_telegram_environment_values_are_exposed_as_settings(self):
        broker = (ROOT / "config/settings/broker.py").read_text(encoding="utf-8")
        base = (ROOT / "config/settings/base.py").read_text(encoding="utf-8")
        self.assertIn('DERIV_OAUTH_CLIENT_SECRET = env("DERIV_OAUTH_CLIENT_SECRET", "")', broker)
        self.assertIn('DERIV_OAUTH_SCOPE = env("DERIV_OAUTH_SCOPE", "trade")', broker)
        self.assertIn('TELEGRAM_MODE = os.getenv("TELEGRAM_MODE", "webhook")', base)
        self.assertIn('TELEGRAM_API_TIMEOUT = os.getenv("TELEGRAM_API_TIMEOUT", "10")', base)
        self.assertIn('TELEGRAM_RETRY_MAX_ATTEMPTS = os.getenv("TELEGRAM_RETRY_MAX_ATTEMPTS", "6")', base)
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertNotIn("DERIV_API_TOKEN=", example)
        self.assertNotIn("OPENAI_API_KEY=", example)
        self.assertNotIn("TELEGRAM_WEBHOOK_URL=", example)

    def test_redis_url_is_the_only_celery_broker_and_backend_configuration(self):
        source = (ROOT / "config/settings/cache.py").read_text(encoding="utf-8")
        self.assertIn("CELERY_BROKER_URL = REDIS_URL", source)
        self.assertIn("CELERY_RESULT_BACKEND = REDIS_URL", source)
        self.assertNotIn('_dotenv_value("CELERY_BROKER_URL"', source)
        self.assertNotIn('_dotenv_value("CELERY_RESULT_BACKEND"', source)
        broker = (ROOT / "config/settings/broker.py").read_text(encoding="utf-8")
        self.assertNotIn('TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID"', broker)
        self.assertNotIn('DERIV_API_BASE = env("DERIV_API_BASE"', broker)

    def test_render_blueprint_does_not_duplicate_celery_urls(self):
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertNotIn('key: CELERY_BROKER_URL', render)
        self.assertNotIn('key: CELERY_RESULT_BACKEND', render)
        self.assertNotIn('CELERY_BROKER_URL="$REDIS_URL"', render)
        self.assertNotIn('CELERY_RESULT_BACKEND="$REDIS_URL"', render)

    def test_repeated_api_errors_are_coalesced_during_polling(self):
        source = (ROOT / "static/js/base_shell.js").read_text(encoding="utf-8")
        self.assertIn("const recentApiErrors = new Map()", source)
        self.assertIn("const API_ERROR_DEDUPE_MS = 10000", source)
        self.assertIn("if(now-previous<API_ERROR_DEDUPE_MS)return", source)

    def test_deriv_tick_watchdog_uses_bounded_backoff_and_recovers_after_valid_tick(self):
        source = (ROOT / "static/js/terminal_market_watchdog.js").read_text(encoding="utf-8")
        self.assertIn("const MAX_RECONNECT_DELAY_MS = 30000", source)
        self.assertIn("Math.min(1000 * (2 ** Math.min(reconnectAttempts, 5)), MAX_RECONNECT_DELAY_MS)", source)
        self.assertIn("reconnectAttempts = 0;", source)
        self.assertIn("closeSocket(); scheduleReconnect(); return;", source)
