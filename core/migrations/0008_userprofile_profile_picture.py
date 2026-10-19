"""Persist device-uploaded profile pictures on user profiles."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0007_unique_user_email_ci")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="profile_picture",
            field=models.ImageField(blank=True, upload_to="profile_pictures/%Y/%m/"),
        ),
    ]
