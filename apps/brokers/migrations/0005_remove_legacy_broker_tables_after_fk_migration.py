from django.db import migrations


# Legacy broker tables are intentionally removed only after the canonical
# brokers models and all dependent app migrations have completed. PostgreSQL
# CASCADE is used here only against these explicitly named legacy tables: it
# removes stale foreign-key constraints that still point at the legacy schema
# without deleting rows from any canonical brokers.* table.
DROP_LEGACY_TABLES = """
DROP TABLE IF EXISTS broker_brokerconnectionlog CASCADE;
DROP TABLE IF EXISTS broker_brokerpermission CASCADE;
DROP TABLE IF EXISTS broker_brokentoken CASCADE;
DROP TABLE IF EXISTS broker_brokeraccount CASCADE;
DROP TABLE IF EXISTS broker_broker CASCADE;
DROP TABLE IF EXISTS trading_derivaccount CASCADE;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0004_merge_broker_migration_heads"),
        ("execution", "0003_use_canonical_broker_account"),
        ("portfolio", "0003_use_canonical_broker_models"),
        ("strategies", "0003_use_canonical_broker_account"),
    ]

    # PostgreSQL DDL must not be held in the same transaction as the earlier
    # data/schema work. This also makes a failed deployment retryable.
    atomic = False

    operations = [
        migrations.RunSQL(
            sql=DROP_LEGACY_TABLES,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
