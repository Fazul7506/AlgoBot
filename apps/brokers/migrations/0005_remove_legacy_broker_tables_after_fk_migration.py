from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0004_merge_broker_migration_heads"),
        ("execution", "0003_use_canonical_broker_account"),
        ("portfolio", "0003_use_canonical_broker_models"),
        ("strategies", "0003_use_canonical_broker_account"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP TABLE IF EXISTS broker_brokerconnectionlog",
                "DROP TABLE IF EXISTS broker_brokerpermission",
                "DROP TABLE IF EXISTS broker_brokentoken",
                "DROP TABLE IF EXISTS broker_brokeraccount",
                "DROP TABLE IF EXISTS broker_broker",
                "DROP TABLE IF EXISTS trading_derivaccount",
            ],
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
