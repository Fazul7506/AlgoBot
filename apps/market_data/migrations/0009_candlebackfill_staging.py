from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("market_data", "0008_rename_market_data_scope_status_req_idx_market_data_scope_793c1f_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CandleBackfillStagedTick",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bid", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("ask", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("quote", models.DecimalField(decimal_places=8, max_digits=20)),
                ("spread", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("epoch", models.BigIntegerField(db_index=True)),
                ("volume", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("received_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="staged_ticks", to="market_data.candlebackfillrun")),
                ("symbol", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="staged_backfill_ticks", to="market_data.marketsymbol")),
            ],
            options={
                "ordering": ["epoch"],
                "unique_together": {("run", "symbol", "epoch", "quote")},
            },
        ),
        migrations.CreateModel(
            name="CandleBackfillStagedCandle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timeframe", models.CharField(choices=[("tick", "tick"), ("1s", "1s"), ("5s", "5s"), ("15s", "15s"), ("30s", "30s"), ("1m", "1m"), ("2m", "2m"), ("5m", "5m"), ("10m", "10m"), ("15m", "15m"), ("30m", "30m"), ("1h", "1h"), ("2h", "2h"), ("4h", "4h"), ("8h", "8h"), ("1d", "1d")], db_index=True, max_length=8)),
                ("open", models.DecimalField(decimal_places=8, max_digits=20)),
                ("high", models.DecimalField(decimal_places=8, max_digits=20)),
                ("low", models.DecimalField(decimal_places=8, max_digits=20)),
                ("close", models.DecimalField(decimal_places=8, max_digits=20)),
                ("volume", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("epoch", models.BigIntegerField(db_index=True)),
                ("source", models.CharField(db_index=True, default="tick_stream", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="staged_candles", to="market_data.candlebackfillrun")),
                ("symbol", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="staged_backfill_candles", to="market_data.marketsymbol")),
            ],
            options={
                "ordering": ["-epoch"],
                "unique_together": {("run", "symbol", "timeframe", "epoch")},
            },
        ),
        migrations.AddIndex(
            model_name="candlebackfillstagedtick",
            index=models.Index(fields=["run", "symbol", "epoch"], name="md_stagedtick_run_sym_epoch"),
        ),
        migrations.AddIndex(
            model_name="candlebackfillstagedcandle",
            index=models.Index(fields=["run", "symbol", "timeframe", "epoch"], name="md_stagedcandle_run_sym_tf_ep"),
        ),
    ]
