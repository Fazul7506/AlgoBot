from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("market_data", "0007_candlebackfill_run_history"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="candlebackfillrun",
            old_name="market_data_scope_status_req_idx",
            new_name="market_data_scope_793c1f_idx",
        ),
        migrations.RenameIndex(
            model_name="candlebackfillrun",
            old_name="market_data_scope_req_idx",
            new_name="market_data_scope_615c5f_idx",
        ),
    ]
