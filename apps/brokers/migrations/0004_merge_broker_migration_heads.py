from django.db import migrations


LEGACY_BROKER_TABLE = "broker_broker"
LEGACY_ACCOUNT_TABLE = "broker_brokeraccount"


def remap_legacy_foreign_keys(apps, schema_editor):
    db = schema_editor.connection
    tables = set(db.introspection.table_names())
    if LEGACY_BROKER_TABLE not in tables or LEGACY_ACCOUNT_TABLE not in tables:
        return

    Broker = apps.get_model("brokers", "Broker")
    BrokerAccount = apps.get_model("brokers", "BrokerAccount")

    with db.cursor() as cursor:
        cursor.execute(f'SELECT id, name, slug FROM "{LEGACY_BROKER_TABLE}" ORDER BY id')
        legacy_brokers = cursor.fetchall()

    broker_map = {}
    for legacy_id, name, slug in legacy_brokers:
        broker_type = str(slug or name or "legacy").lower().replace(" ", "_")[:40]
        canonical = Broker.objects.filter(broker_type=broker_type).first()
        if canonical is None and name:
            canonical = Broker.objects.filter(name=name).first()
        if canonical is None:
            raise RuntimeError(
                f"Cannot safely migrate legacy broker id {legacy_id}: no canonical brokers.Broker exists."
            )
        broker_map[int(legacy_id)] = int(canonical.pk)

    with db.cursor() as cursor:
        cursor.execute(
            f'SELECT id, broker_id, broker_account_id FROM "{LEGACY_ACCOUNT_TABLE}" ORDER BY id'
        )
        legacy_accounts = cursor.fetchall()

    account_map = {}
    for legacy_id, legacy_broker_id, account_id in legacy_accounts:
        canonical_broker_id = broker_map.get(int(legacy_broker_id))
        if canonical_broker_id is None:
            raise RuntimeError(
                f"Cannot safely migrate legacy broker account {legacy_id}: broker mapping is missing."
            )
        canonical = BrokerAccount.objects.filter(
            broker_id=canonical_broker_id, account_id=str(account_id)
        ).first()
        if canonical is None:
            raise RuntimeError(
                f"Cannot safely migrate legacy broker account {legacy_id}: canonical account {account_id!r} is missing."
            )
        account_map[int(legacy_id)] = int(canonical.pk)

    # These updates happen before any legacy tables are removed. The integer FK
    # columns remain intact; only their referenced canonical primary keys change.
    with db.cursor() as cursor:
        for legacy_id, canonical_id in account_map.items():
            cursor.execute(
                "UPDATE execution_order SET broker_account_id = %s WHERE broker_account_id = %s",
                [canonical_id, legacy_id],
            )
            cursor.execute(
                "UPDATE portfolio_portfolioaccount SET broker_account_id = %s WHERE broker_account_id = %s",
                [canonical_id, legacy_id],
            )
            cursor.execute(
                "UPDATE strategies_strategyconfiguration SET broker_account_id = %s WHERE broker_account_id = %s",
                [canonical_id, legacy_id],
            )

        for legacy_id, canonical_id in broker_map.items():
            cursor.execute(
                "UPDATE portfolio_portfolioaccount SET broker_id = %s WHERE broker_id = %s",
                [canonical_id, legacy_id],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0003_alter_broker_broker_type_alter_broker_status"),
        ("brokers", "0003_remove_legacy_broker_tables"),
    ]

    operations = [migrations.RunPython(remap_legacy_foreign_keys, migrations.RunPython.noop)]
