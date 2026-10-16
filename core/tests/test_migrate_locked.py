from unittest.mock import patch

from django.core.management import load_command_class
from django.test import SimpleTestCase


class MigrateLockedCommandTests(SimpleTestCase):
    def test_parser_registers_inherited_migration_options_once(self):
        command = load_command_class("core", "migrate_locked")
        parser = command.create_parser("manage.py", "migrate_locked")

        option_strings = [
            option
            for action in parser._actions
            for option in action.option_strings
        ]

        self.assertEqual(option_strings.count("--verbosity"), 1)
        self.assertEqual(option_strings.count("--database"), 1)
        self.assertIn("--noinput", option_strings)
        self.assertIn("--fake-initial", option_strings)

    @patch("core.management.commands.migrate_locked.call_command")
    def test_delegates_to_locked_migrate_command(self, call_command):
        command = load_command_class("core", "migrate_locked")

        command.handle(
            database="default",
            interactive=False,
            fake_initial=True,
            verbosity=1,
        )

        call_command.assert_called_once_with(
            "migrate",
            database="default",
            interactive=False,
            fake_initial=True,
            verbosity=1,
        )
