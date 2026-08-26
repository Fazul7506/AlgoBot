from django.db import migrations, models


OLD_BROKER_CONNECTION_INDEX = 'brokers_bro_account__f3e4a0_idx'
NEW_BROKER_CONNECTION_INDEX = 'brokers_bro_acct_stat_idx'
OLD_ORDER_INDEX = 'brokers_ord_account__d1f2c7_idx'
NEW_ORDER_INDEX = 'brokers_ord_acct_stat_idx'


def _existing_objects(connection, table):
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, table))


def _find_index(model, name):
    for index in model._meta.indexes:
        if index.name == name:
            return index
    return None


def _safe_rename_index(schema_editor, model, old_name, new_name):
    existing = _existing_objects(schema_editor.connection, model._meta.db_table)
    if new_name in existing or old_name not in existing:
        return

    # Django's rename_index() API in this version expects an Index instance,
    # not an index-name string. On SQLite it may rebuild the table as needed,
    # so use the public remove/add operations with the historical Index state.
    old_index = _find_index(model, old_name)
    if old_index is None:
        return

    new_index = old_index.clone()
    new_index.name = new_name
    schema_editor.remove_index(model, old_index)
    schema_editor.add_index(model, new_index)


def reconcile_index_names(apps, schema_editor):
    BrokerConnection = apps.get_model('brokers', 'BrokerConnection')
    Order = apps.get_model('brokers', 'Order')
    _safe_rename_index(
        schema_editor,
        BrokerConnection,
        OLD_BROKER_CONNECTION_INDEX,
        NEW_BROKER_CONNECTION_INDEX,
    )
    _safe_rename_index(
        schema_editor,
        Order,
        OLD_ORDER_INDEX,
        NEW_ORDER_INDEX,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('brokers', '0002_account_scoped_connections_and_order_idempotency'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(reconcile_index_names, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.RenameIndex(
                    model_name='brokerconnection',
                    old_name=OLD_BROKER_CONNECTION_INDEX,
                    new_name=NEW_BROKER_CONNECTION_INDEX,
                ),
                migrations.RenameIndex(
                    model_name='order',
                    old_name=OLD_ORDER_INDEX,
                    new_name=NEW_ORDER_INDEX,
                ),
            ],
        ),
    ]
