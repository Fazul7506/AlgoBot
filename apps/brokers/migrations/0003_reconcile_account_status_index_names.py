from django.db import migrations


OLD_BROKER_CONNECTION_INDEX = 'brokers_bro_account__f3e4a0_idx'
NEW_BROKER_CONNECTION_INDEX = 'brokers_bro_acct_stat_idx'
OLD_ORDER_INDEX = 'brokers_ord_account__d1f2c7_idx'
NEW_ORDER_INDEX = 'brokers_ord_acct_stat_idx'


def _existing_objects(connection, table):
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, table))


def _safe_rename_index(schema_editor, model, old_name, new_name):
    existing = _existing_objects(schema_editor.connection, model._meta.db_table)
    if new_name in existing or old_name not in existing:
        return
    # Use Django's public schema-editor API. The previous implementation
    # called the private _rename_index_sql() helper directly, which produces
    # SQL that SQLite cannot execute ("near INDEX: syntax error").
    schema_editor.rename_index(model, old_name, new_name)


def reconcile_index_names(apps, schema_editor):
    BrokerConnection = apps.get_model('brokers', 'BrokerConnection')
    Order = apps.get_model('brokers', 'Order')
    _safe_rename_index(schema_editor, BrokerConnection, OLD_BROKER_CONNECTION_INDEX, NEW_BROKER_CONNECTION_INDEX)
    _safe_rename_index(schema_editor, Order, OLD_ORDER_INDEX, NEW_ORDER_INDEX)


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
