import os
from unittest import TestCase
from unittest.mock import patch

from config.settings.database import _database_conn_max_age
from deriv_platform.celery import _close_stale_task_connections, _close_task_connections


class DatabaseConnectionSettingsTests(TestCase):
    def test_supabase_pooler_releases_connections_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DB_CONN_MAX_AGE", None)
            self.assertEqual(
                _database_conn_max_age(
                    "postgresql://postgres.example:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
                ),
                0,
            )

    def test_non_pooler_database_keeps_persistent_connection_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DB_CONN_MAX_AGE", None)
            self.assertEqual(
                _database_conn_max_age(
                    "postgresql://postgres:secret@db.internal.example:5432/postgres"
                ),
                600,
            )

    def test_explicit_connection_age_overrides_pooler_default(self):
        with patch.dict(os.environ, {"DB_CONN_MAX_AGE": "30"}, clear=False):
            self.assertEqual(
                _database_conn_max_age(
                    "postgresql://postgres.example:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
                ),
                30,
            )

    def test_invalid_connection_age_is_rejected(self):
        with patch.dict(os.environ, {"DB_CONN_MAX_AGE": "not-a-number"}, clear=False):
            with self.assertRaisesRegex(ValueError, "DB_CONN_MAX_AGE must be an integer"):
                _database_conn_max_age("postgresql://postgres@db.internal.example:5432/postgres")


class CeleryDatabaseConnectionLifecycleTests(TestCase):
    @patch("deriv_platform.celery.close_old_connections")
    def test_task_prerun_releases_stale_connections(self, close_old_connections):
        _close_stale_task_connections()
        close_old_connections.assert_called_once_with()

    @patch("deriv_platform.celery.close_old_connections")
    def test_task_postrun_releases_obsolete_connections(self, close_old_connections):
        _close_task_connections()
        close_old_connections.assert_called_once_with()
