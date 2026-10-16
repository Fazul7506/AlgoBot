from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.market_data.management.commands.wait_for_market_data_worker_schema import Command


class WaitForMarketDataWorkerSchemaTests(SimpleTestCase):
    @patch("apps.market_data.management.commands.wait_for_market_data_worker_schema.sleep")
    @patch("apps.market_data.management.commands.wait_for_market_data_worker_schema.monotonic", return_value=0)
    @patch("apps.market_data.management.commands.wait_for_market_data_worker_schema.call_command")
    def test_retries_missing_table_then_runs_full_preflight(self, call_command_mock, _monotonic, sleep_mock):
        call_command_mock.side_effect = [
            CommandError("Required database table 'market_data_candlebackfillrun' is missing."),
            None,
        ]

        Command().handle(timeout=30, interval=5)

        self.assertEqual(call_command_mock.call_count, 2)
        sleep_mock.assert_called_once_with(5)

    @patch("apps.market_data.management.commands.wait_for_market_data_worker_schema.call_command")
    def test_non_schema_preflight_failure_fails_fast(self, call_command_mock):
        call_command_mock.side_effect = CommandError("Required Celery runtime variable is missing: REDIS_URL")

        with self.assertRaisesRegex(CommandError, "REDIS_URL"):
            Command().handle(timeout=300, interval=5)

        call_command_mock.assert_called_once()

    @patch("apps.market_data.management.commands.wait_for_market_data_worker_schema.monotonic", side_effect=[0, 301])
    @patch("apps.market_data.management.commands.wait_for_market_data_worker_schema.call_command")
    def test_timeout_is_bounded_and_does_not_echo_database_details(self, call_command_mock, _monotonic):
        call_command_mock.side_effect = CommandError(
            "Required database table 'market_data_candlebackfillrun' is missing."
        )

        with self.assertRaisesRegex(CommandError, "Timed out waiting for the application database schema"):
            Command().handle(timeout=300, interval=5)
