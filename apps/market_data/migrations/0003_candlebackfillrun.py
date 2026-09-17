from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("market_data", "0002_expand_candle_timeframes"),
    ]

    operations = [
        migrations.CreateModel(
            name="CandleBackfillRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(default="initial", max_length=32, unique=True)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed")], db_index=True, default="queued", max_length=20)),
                ("count", models.PositiveIntegerField(default=5000)),
                ("symbol", models.CharField(blank=True, max_length=40)),
                ("task_id", models.CharField(blank=True, db_index=True, max_length=255)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="candle_backfill_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-requested_at"]},
        ),
    ]
