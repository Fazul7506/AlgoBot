from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("execution", "0002_rename_execution_q_status_f45c9d_idx_execution_e_status_3031dd_idx_and_more"),
        ("brokers", "0004_merge_broker_migration_heads"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="broker_account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="execution_orders",
                to="brokers.brokeraccount",
            ),
        ),
    ]
