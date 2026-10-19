"""Disable legacy MFA flags that have no verified secret or recovery codes."""
from django.db import migrations


def disable_unconfigured_mfa(apps, schema_editor):
    UserProfile = apps.get_model("core", "UserProfile")
    UserProfile.objects.filter(
        two_factor_enabled=True,
        two_factor_secret_encrypted="",
    ).update(two_factor_enabled=False)


class Migration(migrations.Migration):
    dependencies = [("core", "0011_userprofile_phone_length")]

    operations = [
        migrations.RunPython(disable_unconfigured_mfa, migrations.RunPython.noop),
    ]
