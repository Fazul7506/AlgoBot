import os
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class MarketDataWorkerPreflightTests(SimpleTestCase):
    @patch("deriv_platform.celery.app")
    @patch.dict(os.environ, {
        "DJANGO_ENV": "production",
        "DATABASE_URL": "postgres://ci",
        "REDIS_URL": "redis://ci",
        "SECRET_KEY": "ci-secret",
        "USE_REDIS": "true",
        "USE_CELERY": "true",
        "CELERY_BROKER_URL": "redis://ci",
        "CELERY_RESULT_BACKEND": "redis://ci",
    }, clear=False)
    def test_preflight_accepts_registered_task_and_market_data_route(self, app):
        app.tasks = {
            "apps.market_data.tasks.run_initial_candle_backfill": object(),
        }
        app.conf.task_routes = {
            "apps.market_data.tasks.run_initial_candle_backfill": {
                "queue": "market_data",
            }
        }
        connection = app.connection_for_read.return_value
        call_command("check_market_data_worker")
        connection.ensure_connection.assert_called_once_with(max_retries=1)

    @patch("deriv_platform.celery.app")
    def test_preflight_rejects_missing_task(self, app):
        app.tasks = {}
        app.conf.task_routes = {}
        with self.assertRaises(CommandError):
            call_command("check_market_data_worker")
