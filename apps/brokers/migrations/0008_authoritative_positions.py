from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0007_alter_broker_broker_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="position",
            name="contract_id",
            field=models.CharField(blank=True, db_index=True, max_length=160),
        ),
        migrations.AddField(
            model_name="position",
            name="transaction_id",
            field=models.CharField(blank=True, db_index=True, max_length=160),
        ),
        migrations.AddField(
            model_name="position",
            name="broker_order_id",
            field=models.CharField(blank=True, db_index=True, max_length=160),
        ),
        migrations.AddField(
            model_name="position",
            name="display_name",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="position",
            name="contract_type",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="position",
            name="stake",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
        ),
        migrations.AddField(
            model_name="position",
            name="exit_price",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
        ),
        migrations.AddField(
            model_name="position",
            name="payout",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
        ),
        migrations.AddField(
            model_name="position",
            name="currency",
            field=models.CharField(blank=True, max_length=12),
        ),
        migrations.AddField(
            model_name="position",
            name="expiry_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="position",
            name="settlement_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="position",
            name="broker_timestamp",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="position",
            name="last_synced_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="position",
            name="raw_data",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="position",
            name="symbol",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AlterField(
            model_name="position",
            name="direction",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AlterField(
            model_name="position",
            name="size",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
        ),
        migrations.AlterField(
            model_name="position",
            name="entry_price",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
        ),
        migrations.AlterField(
            model_name="position",
            name="current_price",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
        ),
        migrations.AlterField(
            model_name="position",
            name="profit",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True),
        ),
        migrations.AlterField(
            model_name="position",
            name="status",
            field=models.CharField(db_index=True, default="unknown", max_length=40),
        ),
        migrations.AlterField(
            model_name="position",
            name="opened_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="position",
            constraint=models.UniqueConstraint(
                condition=~models.Q(contract_id=""),
                fields=("account", "contract_id"),
                name="unique_broker_position_contract",
            ),
        ),
        migrations.AddIndex(
            model_name="position",
            index=models.Index(fields=["account", "status", "-broker_timestamp"], name="bro_pos_acct_status_time_idx"),
        ),
        migrations.AddIndex(
            model_name="position",
            index=models.Index(fields=["account", "symbol", "status"], name="bro_pos_acct_symbol_status_idx"),
        ),
    ]
