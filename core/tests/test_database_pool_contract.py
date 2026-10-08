import os
from unittest.mock import patch

from django.test import SimpleTestCase

from config.settings.database import _database_pool_options


class DatabasePoolContractTests(SimpleTestCase):
    def test_production_pool_is_bounded_for_supabase_pooler(self):
        with patch.dict(os.environ, {"DJANGO_ENV": "production"}, clear=False):
            options = _database_pool_options(
                "postgresql://postgres.example:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
            )

        self.assertEqual(options["pool"]["min_size"], 1)
        self.assertEqual(options["pool"]["max_size"], 3)
        self.assertEqual(options["pool"]["max_lifetime"], 1800)
        self.assertEqual(options["pool"]["timeout"], 10)
        self.assertTrue(options["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertFalse(options["server_side_binding"])

    def test_pool_can_be_disabled_for_local_or_legacy_runtime(self):
        with patch.dict(os.environ, {"DJANGO_ENV": "development", "DB_CONNECTION_POOL_ENABLED": "false"}, clear=False):
            self.assertEqual(
                _database_pool_options(
                    "postgresql://postgres@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
                ),
                {},
            )

    def test_invalid_pool_bounds_fail_fast(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_ENV": "production",
                "DB_POOL_MIN_SIZE": "4",
                "DB_POOL_MAX_SIZE": "3",
            },
            clear=False,
        ):
            with self.assertRaises(ValueError):
                _database_pool_options(
                    "postgresql://postgres@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
                )
