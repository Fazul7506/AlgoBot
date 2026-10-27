"""Record acceptance of the Terms of Service during profile onboarding."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0010_userprofile_picture_database_storage")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="terms_accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
