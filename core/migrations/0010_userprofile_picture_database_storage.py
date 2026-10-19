"""Store normalized profile pictures durably in the database."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0009_userprofile_totp_enrollment")]

    operations = [
        migrations.RemoveField(
            model_name="userprofile",
            name="profile_picture",
        ),
        migrations.AddField(
            model_name="userprofile",
            name="profile_picture_data",
            field=models.BinaryField(blank=True, default=bytes),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="profile_picture_content_type",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
