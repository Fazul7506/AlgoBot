# Generated manually from apps.market_data.models.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketSymbol",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("broker", models.CharField(default="deriv", max_length=80)),
                ("symbol", models.CharField(db_index=True, max_length=40, unique=True)),
                ("display_name", models.CharField(max_length=160)),
                ("market", models.CharField(choices=[], db_index=True, max_length=80)),
                ("sub_market", models.CharField(blank=True, db_index=True, max_length=120)),
                ("pip_size", models.PositiveSmallIntegerField(default=2)),
                ("tick_size", models.DecimalField(decimal_places=8, default=0, max_digits=18)),
                ("currency", models.CharField(blank=True, max_length=12)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("is_tradable", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["market", "symbol"],
                "indexes": [
                    models.Index(fields=["broker", "symbol"], name="market_data_broker_7a0a9c_idx"),
                    models.Index(fields=["market", "sub_market"], name="market_data_market_4f7b32_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Tick",
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
                ("symbol", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ticks", to="market_data.marketsymbol")),
            ],
            options={
                "ordering": ["-epoch"],
                "unique_together": {("symbol", "epoch", "quote")},
                "indexes": [
                    models.Index(fields=["symbol", "-epoch"], name="market_data_symbol_2a3d5b_idx"),
                    models.Index(fields=["received_at"], name="market_data_receive_2c8a1d_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Candle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timeframe", models.CharField(choices=[], db_index=True, max_length=8)),
                ("open", models.DecimalField(decimal_places=8, max_digits=20)),
                ("high", models.DecimalField(decimal_places=8, max_digits=20)),
                ("low", models.DecimalField(decimal_places=8, max_digits=20)),
                ("close", models.DecimalField(decimal_places=8, max_digits=20)),
                ("volume", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("epoch", models.BigIntegerField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("symbol", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="candles", to="market_data.marketsymbol")),
            ],
            options={
                "ordering": ["-epoch"],
                "unique_together": {("symbol", "timeframe", "epoch")},
                "indexes": [models.Index(fields=["symbol", "timeframe", "-epoch"], name="market_data_symbol_9c4a0d_idx")],
            },
        ),
        migrations.CreateModel(
            name="MarketSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_price", models.DecimalField(decimal_places=8, max_digits=20)),
                ("bid", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("ask", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("spread", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("high", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("low", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("change", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("change_percent", models.DecimalField(decimal_places=4, default=0, max_digits=10)),
                ("volume", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("timestamp", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("symbol", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="snapshot", to="market_data.marketsymbol")),
            ],
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timeframe", models.CharField(default="tick", max_length=8)),
                ("status", models.CharField(choices=[("active", "Active"), ("paused", "Paused"), ("cancelled", "Cancelled")], db_index=True, default="active", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("symbol", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subscriptions", to="market_data.marketsymbol")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="market_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"unique_together": {("user", "symbol", "timeframe")}},
        ),
        migrations.CreateModel(
            name="MarketStatistics",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("average_spread", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("highest_price", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("lowest_price", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("highest_volume", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("tick_count", models.PositiveBigIntegerField(default=0)),
                ("average_tick_rate", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("market_volatility", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("average_volume", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("tick_frequency", models.DecimalField(decimal_places=8, default=0, max_digits=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("symbol", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="statistics", to="market_data.marketsymbol")),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["symbol", "-created_at"], name="market_data_symbol_1d4c8e_idx")],
            },
        ),
    ]
