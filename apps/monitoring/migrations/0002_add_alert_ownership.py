from django.conf import settings
from django.db import migrations, models
from django.db.models.deletion import CASCADE


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=CASCADE,
                related_name="alerts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["user", "-created_at"], name="monitoring_alert_user_idx"),
        ),
    ]
