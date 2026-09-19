from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("market_data", "0005_merge_0004_candle_source_and_backfill_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="candlebackfillrun",
            name="accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="candlebackfillrun",
            name="current_symbol",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="candlebackfillrun",
            name="current_timeframe",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="candlebackfillrun",
            name="dispatch_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="candlebackfillrun",
            name="last_heartbeat_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="candlebackfillrun",
            name="worker_hostname",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.CreateModel(
            name="CandleBackfillEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("level", models.CharField(choices=[("info", "Info"), ("notice", "Notice"), ("warning", "Warning"), ("error", "Error"), ("success", "Success")], db_index=True, default="info", max_length=16)),
                ("event_type", models.CharField(choices=[("dispatch", "Dispatch"), ("worker_received", "Worker received"), ("worker_started", "Worker started"), ("symbol_started", "Symbol started"), ("timeframe", "Timeframe"), ("symbol_completed", "Symbol completed"), ("heartbeat", "Heartbeat"), ("warning", "Warning"), ("error", "Error"), ("completed", "Completed"), ("failed", "Failed"), ("recovered", "Recovered")], default="heartbeat", max_length=32)),
                ("message", models.TextField()),
                ("symbol", models.CharField(blank=True, max_length=40)),
                ("timeframe", models.CharField(blank=True, max_length=32)),
                ("task_id", models.CharField(blank=True, max_length=255)),
                ("worker_hostname", models.CharField(blank=True, max_length=255)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="market_data.candlebackfillrun")),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="candlebackfillevent",
            index=models.Index(fields=["run", "-created_at"], name="market_data_c_run_id_7b7b9c_idx"),
        ),
        migrations.AddIndex(
            model_name="candlebackfillevent",
            index=models.Index(fields=["run", "level", "-created_at"], name="market_data_c_run_id_3b3f8e_idx"),
        ),
    ]
