"""Allow canonical international phone values up to 32 characters."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0010_userprofile_picture_database_storage")]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="phone",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
