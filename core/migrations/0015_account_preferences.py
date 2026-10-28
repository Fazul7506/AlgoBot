"""Persist non-secret account UI preferences without touching existing user data."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_merge_profile_onboarding"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="account_preferences",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
