from django.conf import settings
from django.db import migrations, models
from django.db.models.deletion import CASCADE


class Migration(migrations.Migration):
    dependencies = [
        ("deployment", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="deploymentrecord",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=CASCADE,
                related_name="deployment_records",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="backuprecord",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=CASCADE,
                related_name="backup_records",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
