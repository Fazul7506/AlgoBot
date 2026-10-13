from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("market_data", "0009_candlebackfill_staging"),
    ]

    operations = [
        migrations.AlterField(
            model_name="candlebackfillrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("stopped", "Stopped"),
                ],
                db_index=True,
                default="running",
                max_length=20,
            ),
        ),
    ]
