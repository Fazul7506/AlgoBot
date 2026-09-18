from django.db import migrations, models


def normalize_queued_runs(apps, schema_editor):
    CandleBackfillRun = apps.get_model("market_data", "CandleBackfillRun")
    CandleBackfillRun.objects.filter(status__in=["queued", "succeeded"]).update(status="running")


class Migration(migrations.Migration):

    dependencies = [
        ("market_data", "0003_candlebackfillrun"),
    ]

    operations = [
        migrations.RunPython(
            normalize_queued_runs,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="candlebackfillrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="running",
                max_length=20,
            ),
        ),
    ]
