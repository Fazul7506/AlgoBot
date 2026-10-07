from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("market_data", "0006_candlebackfill_telemetry"),
    ]

    operations = [
        migrations.AlterField(
            model_name="candlebackfillrun",
            name="scope",
            field=models.CharField(db_index=True, default="initial", max_length=32),
        ),
        migrations.AddField(
            model_name="candlebackfillrun",
            name="run_key",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddIndex(
            model_name="candlebackfillrun",
            index=models.Index(fields=["scope", "status", "-requested_at"], name="market_data_scope_status_req_idx"),
        ),
        migrations.AddIndex(
            model_name="candlebackfillrun",
            index=models.Index(fields=["scope", "-requested_at"], name="market_data_scope_req_idx"),
        ),
    ]
