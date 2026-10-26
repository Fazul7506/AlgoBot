# Generated to add the broker-supported three-minute interval without rewriting
# the original migration history.
from django.db import migrations, models


TIMEFRAME_CHOICES = [('tick', 'tick'), ('1s', '1s'), ('5s', '5s'), ('15s', '15s'), ('30s', '30s'), ('1m', '1m'), ('2m', '2m'), ('3m', '3m'), ('5m', '5m'), ('10m', '10m'), ('15m', '15m'), ('30m', '30m'), ('1h', '1h'), ('2h', '2h'), ('4h', '4h'), ('8h', '8h'), ('1d', '1d')]


class Migration(migrations.Migration):
    dependencies = [
        ("market_data", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="candle",
            name="timeframe",
            field=models.CharField(choices=TIMEFRAME_CHOICES, db_index=True, max_length=8),
        ),
        migrations.AlterField(
            model_name="subscription",
            name="timeframe",
            field=models.CharField(choices=TIMEFRAME_CHOICES, default="tick", max_length=8),
        ),
    ]
