from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("brokers", "0002_canonicalize_legacy_broker_data")]

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
