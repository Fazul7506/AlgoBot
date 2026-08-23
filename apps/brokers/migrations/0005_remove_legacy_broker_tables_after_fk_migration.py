from django.db import migrations


# PostgreSQL can retain stale foreign-key constraints to the historical
# apps.broker tables when an earlier deployment was partially migrated or a
# migration was faked. Remove only constraints whose target is one of the
# legacy tables before dropping those tables. Canonical brokers.* foreign keys
# point to different tables and are not touched.
DROP_LEGACY_FOREIGN_KEYS = """
DO $$
DECLARE
    constraint_row RECORD;
BEGIN
    FOR constraint_row IN
        SELECT
            ns.nspname AS schema_name,
            cls.relname AS table_name,
            con.conname AS constraint_name
        FROM pg_constraint con
        JOIN pg_class cls ON cls.oid = con.conrelid
        JOIN pg_namespace ns ON ns.oid = cls.relnamespace
        JOIN pg_class target_cls ON target_cls.oid = con.confrelid
        JOIN pg_namespace target_ns ON target_ns.oid = target_cls.relnamespace
        WHERE con.contype = 'f'
          AND target_ns.nspname = 'public'
          AND target_cls.relname IN (
              'broker_broker',
              'broker_brokeraccount',
              'broker_brokentoken',
              'broker_brokerconnectionlog',
              'broker_brokerpermission',
              'trading_derivaccount'
          )
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I DROP CONSTRAINT IF EXISTS %I',
            constraint_row.schema_name,
            constraint_row.table_name,
            constraint_row.constraint_name
        );
    END LOOP;
END $$;
"""


DROP_LEGACY_TABLES = """
DROP TABLE IF EXISTS broker_brokerconnectionlog;
DROP TABLE IF EXISTS broker_brokerpermission;
DROP TABLE IF EXISTS broker_brokentoken;
DROP TABLE IF EXISTS broker_brokeraccount;
DROP TABLE IF EXISTS broker_broker;
DROP TABLE IF EXISTS trading_derivaccount;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0004_merge_broker_migration_heads"),
        ("execution", "0003_use_canonical_broker_account"),
        ("portfolio", "0003_use_canonical_broker_models"),
        ("strategies", "0003_use_canonical_broker_account"),
    ]

    # Keep DDL outside one long transaction. The operation is conditional and
    # therefore safe to retry after a failed deployment.
    atomic = False

    operations = [
        migrations.RunSQL(
            sql=DROP_LEGACY_FOREIGN_KEYS,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=DROP_LEGACY_TABLES,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
