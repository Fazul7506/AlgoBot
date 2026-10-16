"""Serialize Django migrations across shared-database services.

This overrides Django's built-in migrate command. It protects legacy/manual
deployment commands as well as explicitly configured migrate_locked commands.
"""
from django.core.management.commands.migrate import Command as DjangoMigrateCommand
from django.db import connections


_MIGRATION_LOCK_ID = 734_920_561_104_221


class Command(DjangoMigrateCommand):
    help = "Run Django migrations while holding a PostgreSQL advisory lock."

    def handle(self, *args, **options):
        connection = connections[options["database"]]
        if connection.vendor != "postgresql":
            return super().handle(*args, **options)

        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [_MIGRATION_LOCK_ID])
        try:
            self.stdout.write("Acquired database migration lock.")
            return super().handle(*args, **options)
        finally:
            # Session locks are released explicitly; PostgreSQL also releases
            # them when the connection closes unexpectedly.
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
