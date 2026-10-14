"""Add race-safe, case-insensitive uniqueness for local account email addresses.

Existing duplicate email records are never deleted or merged automatically. The
migration stops with a safe error if historical duplicates need operator review.
"""
from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower


EMAIL_INDEX_NAME = "auth_user_email_ci_uniq"
USERNAME_INDEX_NAME = "auth_user_username_ci_uniq"


def add_email_unique_index(apps, schema_editor):
    User = apps.get_model("auth", "User")
    duplicate_exists = (
        User.objects.exclude(email__isnull=True)
        .exclude(email="")
        .annotate(normalized_email=Lower("email"))
        .values("normalized_email")
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
        .exists()
    )
    duplicate_username_exists = (
        User.objects.annotate(normalized_username=Lower("username"))
        .values("normalized_username")
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
        .exists()
    )
    if duplicate_exists or duplicate_username_exists:
        raise RuntimeError(
            "Cannot enforce case-insensitive unique account emails/usernames: "
            "existing duplicates require manual reconciliation. No user records were changed."
        )

    vendor = schema_editor.connection.vendor
    if vendor not in {"postgresql", "sqlite"}:
        raise RuntimeError(
            "The account-email uniqueness migration supports PostgreSQL and SQLite only."
        )
    table = schema_editor.quote_name(User._meta.db_table)
    column = schema_editor.quote_name("email")
    email_index = schema_editor.quote_name(EMAIL_INDEX_NAME)
    username_index = schema_editor.quote_name(USERNAME_INDEX_NAME)
    username_column = schema_editor.quote_name("username")
    schema_editor.execute(
        f"CREATE UNIQUE INDEX {email_index} ON {table} (LOWER({column})) "
        f"WHERE {column} IS NOT NULL AND {column} <> ''"
    )
    schema_editor.execute(
        f"CREATE UNIQUE INDEX {username_index} ON {table} (LOWER({username_column}))"
    )


def drop_email_unique_index(apps, schema_editor):
    schema_editor.execute(
        f"DROP INDEX IF EXISTS {schema_editor.quote_name(USERNAME_INDEX_NAME)}"
    )
    schema_editor.execute(
        f"DROP INDEX IF EXISTS {schema_editor.quote_name(EMAIL_INDEX_NAME)}"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_email_verification_token_expiry"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(add_email_unique_index, drop_email_unique_index),
    ]
