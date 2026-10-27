from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0012_disable_legacy_unconfigured_mfa")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="gender",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
