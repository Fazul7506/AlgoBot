from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("market_data", "0004_candle_source"),
        ("market_data", "0004_remove_queued_backfill_status"),
    ]

    operations = []
