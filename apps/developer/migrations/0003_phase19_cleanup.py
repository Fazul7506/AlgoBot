from django.db import migrations, models
from django.utils import timezone


def backfill_timestamps(apps, schema_editor):
    APIKey = apps.get_model("developer", "APIKey")
    Webhook = apps.get_model("developer", "Webhook")
    now = timezone.now()
    APIKey.objects.filter(created_at__isnull=True).update(created_at=now)
    APIKey.objects.filter(updated_at__isnull=True).update(updated_at=now)
    Webhook.objects.filter(created_at__isnull=True).update(created_at=now)
    Webhook.objects.filter(updated_at__isnull=True).update(updated_at=now)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("developer", "0002_phase19_platform")]

    operations = [
        migrations.RunPython(backfill_timestamps, noop),
        migrations.AddField(
            model_name="apikey",
            name="previous_secret",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="apikey",
            name="previous_secret_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="apikey",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="apikey",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="webhook",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="webhook",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
