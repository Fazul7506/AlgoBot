from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("market_data", "0003_candlebackfillrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="candle",
            name="source",
            field=models.CharField(db_index=True, default="tick_stream", max_length=32),
        ),
    ]
