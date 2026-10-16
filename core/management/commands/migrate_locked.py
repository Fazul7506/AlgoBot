"""Serialize schema migrations across concurrent web/worker deployments.

PostgreSQL session-level advisory locks prevent two independent deployment
processes from applying the same Django migration at the same time. This is
especially important when multiple services share one production database.
"""
from django.core.management import BaseCommand, call_command
from django.db import connections


# Stable, application-specific signed 64-bit key reserved for migration runs.
_MIGRATION_LOCK_ID = 734_920_561_104_221


class Command(BaseCommand):
    help = "Run Django migrations while holding a PostgreSQL advisory lock."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument("--noinput", action="store_true")
        parser.add_argument("--verbosity", type=int, default=1)

    def handle(self, *args, **options):
        database = options["database"]
        connection = connections[database]
        migrate_options = {
            "database": database,
            "interactive": not options["noinput"],
            "verbosity": options["verbosity"],
        }

        # SQLite and other non-PostgreSQL backends have no PostgreSQL advisory
        # lock. Keep local/test behavior identical to Django's normal command.
        if connection.vendor != "postgresql":
            call_command("migrate", **migrate_options)
            return

        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [_MIGRATION_LOCK_ID])
        try:
            self.stdout.write("Acquired database migration lock.")
            call_command("migrate", **migrate_options)
        finally:
            # Release the session lock even when a migration fails. Use a
            # fresh cursor on the same connection, and don't mask the original
            # migration exception if the connection itself has failed.
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [_MIGRATION_LOCK_ID])
            except Exception:
                self.stderr.write(
                    self.style.WARNING(
                        "Could not explicitly release migration lock; "
                        "the database connection will release it when closed."
                    )
                )
