from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("market_data", "0002_add_three_minute_timeframe"),
    ]

    operations = [
        migrations.AddField(
            model_name="tick",
            name="bid_ask_source",
            field=models.CharField(
                choices=[
                    ("unknown", "Unknown legacy provenance"),
                    ("broker", "Broker-provided bid and ask"),
                    ("partial", "Partial broker-provided quote"),
                    ("unavailable", "Not supplied by broker"),
                ],
                db_index=True,
                default="unknown",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="marketsnapshot",
            name="bid_ask_source",
            field=models.CharField(
                choices=[
                    ("unknown", "Unknown legacy provenance"),
                    ("broker", "Broker-provided bid and ask"),
                    ("partial", "Partial broker-provided quote"),
                    ("unavailable", "Not supplied by broker"),
                ],
                db_index=True,
                default="unknown",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="marketstatistics",
            name="spread_sample_count",
            field=models.PositiveBigIntegerField(default=0),
        ),
    ]
