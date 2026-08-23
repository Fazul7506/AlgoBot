from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("strategies", "0002_rename_strategies_s_enabled_51dc7f_idx_strategies__enabled_aaadb9_idx_and_more"),
        ("brokers", "0004_merge_broker_migration_heads"),
    ]

    operations = [
        migrations.AlterField(
            model_name="strategyconfiguration",
            name="broker_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="strategy_configurations",
                to="brokers.brokeraccount",
            ),
        ),
    ]
