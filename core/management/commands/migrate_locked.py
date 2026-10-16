"""Compatibility alias for the advisory-locking migrate command.

The inherited Django migration parser defines all supported migration options.
Delegating to the custom migrate command keeps locking centralized and avoids
re-declaring argparse options that Django already registered.
"""
from django.core.management import call_command
from django.core.management.commands.migrate import Command as DjangoMigrateCommand


class Command(DjangoMigrateCommand):
    help = "Run Django migrations using the PostgreSQL advisory-locked command."

    def handle(self, *args, **options):
        return call_command("migrate", *args, **options)
