"""Compatibility alias for the advisory-locking migrate command.

Kept so deployment configurations can use an explicit, self-documenting
command name. The custom migrate command owns the lock so even legacy
python manage.py migrate invocations are serialized.
"""
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "Run Django migrations using the PostgreSQL advisory-locked command."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument("--noinput", action="store_true")
        parser.add_argument("--fake-initial", action="store_true")
        parser.add_argument("--verbosity", type=int, default=1)

    def handle(self, *args, **options):
        migrate_options = {
            "database": options["database"],
            "interactive": not options["noinput"],
            "verbosity": options["verbosity"],
        }
        if options.get("fake_initial"):
            migrate_options["fake_initial"] = True
        return call_command("migrate", **migrate_options)
