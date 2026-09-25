from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("execution", "0006_rename_execution_o_broker__8f7b11_idx_execution_o_broker__46084b_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="BrokerTradeHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("broker_contract_id", models.CharField(blank=True, db_index=True, max_length=160, null=True)),
                ("broker_transaction_id", models.CharField(blank=True, db_index=True, max_length=160, null=True)),
                ("broker_order_id", models.CharField(blank=True, max_length=160, null=True)),
                ("reference_id", models.CharField(blank=True, max_length=160, null=True)),
                ("symbol", models.CharField(blank=True, max_length=80, null=True)),
                ("display_name", models.CharField(blank=True, max_length=160, null=True)),
                ("instrument_type", models.CharField(blank=True, max_length=80, null=True)),
                ("contract_type", models.CharField(blank=True, max_length=80, null=True)),
                ("direction", models.CharField(blank=True, max_length=32, null=True)),
                ("duration", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("duration_unit", models.CharField(blank=True, max_length=8, null=True)),
                ("barrier", models.CharField(blank=True, max_length=160, null=True)),
                ("buy_price", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("entry_price", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("sell_price", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("exit_price", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("stake", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("payout", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("profit_loss", models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True)),
                ("currency", models.CharField(blank=True, max_length=12, null=True)),
                ("status", models.CharField(default="unknown", max_length=40)),
                ("purchase_time", models.DateTimeField(blank=True, null=True)),
                ("execution_time", models.DateTimeField(blank=True, null=True)),
                ("settlement_time", models.DateTimeField(blank=True, null=True)),
                ("expiry_time", models.DateTimeField(blank=True, null=True)),
                ("broker_timestamp", models.DateTimeField(blank=True, null=True)),
                ("raw_data", models.JSONField(blank=True, default=dict)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="broker_trade_history", to="auth.user")),
                ("broker_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="broker_trade_history", to="brokers.brokeraccount")),
            ],
            options={"ordering": ["-broker_timestamp", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="brokertradehistory",
            constraint=models.UniqueConstraint(
                condition=~models.Q(broker_contract_id=""),
                fields=("broker_account", "broker_contract_id"),
                name="unique_trade_contract_per_account",
            ),
        ),
        migrations.AddConstraint(
            model_name="brokertradehistory",
            constraint=models.UniqueConstraint(
                condition=~models.Q(broker_transaction_id=""),
                fields=("broker_account", "broker_transaction_id"),
                name="unique_trade_transaction_per_account",
            ),
        ),
        migrations.AddIndex(
            model_name="brokertradehistory",
            index=models.Index(fields=["broker_account", "broker_timestamp"], name="execution_t_account_time_idx"),
        ),
        migrations.AddIndex(
            model_name="brokertradehistory",
            index=models.Index(fields=["broker_account", "symbol", "status"], name="exec_t_acct_sym_status_idx"),
        ),
    ]
