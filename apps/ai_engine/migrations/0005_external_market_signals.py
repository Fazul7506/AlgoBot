from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai_engine", "0004_add_ai_artifact_ownership"),
    ]

    operations = [
        migrations.CreateModel(
            name="SentimentObservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(db_index=True, max_length=40)),
                ("source", models.CharField(max_length=500)),
                ("source_url", models.URLField(blank=True, max_length=1000)),
                ("content_hash", models.CharField(max_length=64)),
                ("published_at", models.DateTimeField(db_index=True)),
                ("compound", models.FloatField()),
                ("positive", models.FloatField()),
                ("neutral", models.FloatField()),
                ("negative", models.FloatField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-published_at"], "constraints": [models.UniqueConstraint(fields=("symbol", "content_hash"), name="ai_sentiment_symbol_content_uniq")]},
        ),
        migrations.CreateModel(
            name="OrderBookSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(db_index=True, max_length=40)),
                ("observed_at", models.DateTimeField(db_index=True)),
                ("bid_volume", models.FloatField()),
                ("ask_volume", models.FloatField()),
                ("imbalance", models.FloatField()),
                ("spread_bps", models.FloatField()),
            ],
            options={"ordering": ["-observed_at"], "indexes": [models.Index(fields=["symbol", "-observed_at"], name="ai_orderbook_sym_time_idx")]},
        ),
    ]
