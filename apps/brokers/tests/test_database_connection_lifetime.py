import os
from unittest.mock import patch

from django.test import SimpleTestCase

from config.settings.database import _database_conn_max_age


class DatabaseConnectionLifetimeTests(SimpleTestCase):
    def test_production_defaults_to_request_scoped_connections(self):
        with patch.dict(os.environ, {"DJANGO_ENV": "production", "RENDER": ""}), patch(
            "config.settings.database.env", return_value=""
        ):
            self.assertEqual(
                _database_conn_max_age("postgresql://user:pass@dpg-example.render.com/db"),
                0,
            )

    def test_render_deployment_defaults_to_request_scoped_connections(self):
        with patch.dict(os.environ, {"DJANGO_ENV": "development", "RENDER": "true"}), patch(
            "config.settings.database.env", return_value=""
        ):
            self.assertEqual(
                _database_conn_max_age("postgresql://user:pass@dpg-example.render.com/db"),
                0,
            )

    def test_development_keeps_existing_default(self):
        with patch.dict(os.environ, {"DJANGO_ENV": "development", "RENDER": ""}), patch(
            "config.settings.database.env", return_value=""
        ):
            self.assertEqual(
                _database_conn_max_age("postgresql://user:pass@localhost/db"),
                600,
            )

    def test_explicit_connection_lifetime_remains_respected(self):
        with patch.dict(os.environ, {"DJANGO_ENV": "production", "RENDER": ""}), patch(
            "config.settings.database.env",
            side_effect=lambda key, default="": "120" if key == "DB_CONN_MAX_AGE" else default,
        ):
            self.assertEqual(
                _database_conn_max_age("postgresql://user:pass@dpg-example.render.com/db"),
                120,
            )
