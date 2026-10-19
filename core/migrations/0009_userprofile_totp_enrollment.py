"""Add encrypted TOTP enrollment and hashed recovery-code state."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0008_userprofile_profile_picture")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="two_factor_secret_encrypted",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="two_factor_pending_secret_encrypted",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="two_factor_recovery_codes",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
