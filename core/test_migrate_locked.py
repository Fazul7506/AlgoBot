from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase

from core.management.commands.migrate_locked import Command, _MIGRATION_LOCK_ID


class MigrateLockedCommandTests(SimpleTestCase):
    @patch("core.management.commands.migrate_locked.call_command")
    @patch("core.management.commands.migrate_locked.connections")
    def test_postgres_migrations_are_locked_and_lock_is_released(self, connections, call_command_mock):
        connection = MagicMock()
        connection.vendor = "postgresql"
        connections.__getitem__.return_value = connection

        Command().handle(noinput=True, verbosity=0, database="default")

        connection.ensure_connection.assert_called_once_with()
        self.assertEqual(connection.cursor.return_value.__enter__.return_value.execute.call_args_list, [
            call("SELECT pg_advisory_lock(%s)", [_MIGRATION_LOCK_ID]),
            call("SELECT pg_advisory_unlock(%s)", [_MIGRATION_LOCK_ID]),
        ])
        call_command_mock.assert_called_once_with(
            "migrate", database="default", interactive=False, verbosity=0
        )

    @patch("core.management.commands.migrate_locked.call_command", side_effect=RuntimeError("migration failed"))
    @patch("core.management.commands.migrate_locked.connections")
    def test_postgres_lock_is_released_when_migration_fails(self, connections, call_command_mock):
        connection = MagicMock()
        connection.vendor = "postgresql"
        connections.__getitem__.return_value = connection

        with self.assertRaisesRegex(RuntimeError, "migration failed"):
            Command().handle(noinput=True, verbosity=0, database="default")

        self.assertEqual(connection.cursor.return_value.__enter__.return_value.execute.call_count, 2)

    @patch("core.management.commands.migrate_locked.call_command")
    @patch("core.management.commands.migrate_locked.connections")
    def test_non_postgres_backend_uses_standard_migrate(self, connections, call_command_mock):
        connection = MagicMock()
        connection.vendor = "sqlite"
        connections.__getitem__.return_value = connection

        Command().handle(noinput=True, verbosity=0, database="default")

        connection.ensure_connection.assert_not_called()
        call_command_mock.assert_called_once_with(
            "migrate", database="default", interactive=False, verbosity=0
        )
