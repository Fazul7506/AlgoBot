from unittest.mock import MagicMock, call, patch

from django.core.management import get_commands
from django.test import SimpleTestCase

from core.management.commands.migrate import Command as LockedMigrateCommand, _MIGRATION_LOCK_ID
from core.management.commands.migrate_locked import Command as MigrateLockedAlias


class LockedMigrateCommandTests(SimpleTestCase):
    @patch("core.management.commands.migrate.connections")
    @patch("core.management.commands.migrate.DjangoMigrateCommand.handle", return_value="migrated")
    def test_postgres_migrations_are_locked_and_lock_is_released(self, parent_handle, connections):
        connection = MagicMock()
        connection.vendor = "postgresql"
        connections.__getitem__.return_value = connection

        result = LockedMigrateCommand().handle(database="default", verbosity=0, interactive=False)

        self.assertEqual(result, "migrated")
        connection.ensure_connection.assert_called_once_with()
        self.assertEqual(
            connection.cursor.return_value.__enter__.return_value.execute.call_args_list,
            [
                call("SELECT pg_advisory_lock(%s)", [_MIGRATION_LOCK_ID]),
                call("SELECT pg_advisory_unlock(%s)", [_MIGRATION_LOCK_ID]),
            ],
        )
        parent_handle.assert_called_once_with(database="default", verbosity=0, interactive=False)

    @patch("core.management.commands.migrate.connections")
    @patch("core.management.commands.migrate.DjangoMigrateCommand.handle", side_effect=RuntimeError("migration failed"))
    def test_lock_is_released_when_migration_fails(self, parent_handle, connections):
        connection = MagicMock()
        connection.vendor = "postgresql"
        connections.__getitem__.return_value = connection

        with self.assertRaisesRegex(RuntimeError, "migration failed"):
            LockedMigrateCommand().handle(database="default", verbosity=0, interactive=False)

        self.assertEqual(connection.cursor.return_value.__enter__.return_value.execute.call_count, 2)

    @patch("core.management.commands.migrate.connections")
    @patch("core.management.commands.migrate.DjangoMigrateCommand.handle", return_value="migrated")
    def test_non_postgres_backend_uses_standard_migrate(self, parent_handle, connections):
        connection = MagicMock()
        connection.vendor = "sqlite"
        connections.__getitem__.return_value = connection

        LockedMigrateCommand().handle(database="default", verbosity=0, interactive=False)

        connection.ensure_connection.assert_not_called()
        parent_handle.assert_called_once_with(database="default", verbosity=0, interactive=False)

    def test_builtin_migrate_command_is_overridden_by_core(self):
        self.assertEqual(get_commands()["migrate"], "core")


class MigrateLockedAliasTests(SimpleTestCase):
    @patch("core.management.commands.migrate_locked.call_command")
    def test_alias_forwards_fake_initial_and_noinput(self, call_command_mock):
        MigrateLockedAlias().handle(
            database="default", interactive=False, fake_initial=True, verbosity=0
        )
        call_command_mock.assert_called_once_with(
            "migrate",
            database="default",
            interactive=False,
            fake_initial=True,
            verbosity=0,
        )
