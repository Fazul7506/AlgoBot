from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


def _existing_db_objects(connection, table):
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table)
    return set(constraints)


def ensure_broker_account_column(apps, schema_editor):
    """Reconcile broker_account_id without relying on the post-migration model state."""
    connection = schema_editor.connection
    table = 'brokers_brokerconnection'
    with connection.cursor() as cursor:
        columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table)
        }

    if 'broker_account_id' in columns:
        return

    # This RunPython operation executes before the state AddField below.  The
    # historical BrokerConnection model therefore cannot contain
    # ``broker_account`` yet. Build the historical field explicitly instead of
    # calling BrokerConnection._meta.get_field(), which raises FieldDoesNotExist.
    BrokerConnection = apps.get_model('brokers', 'BrokerConnection')
    BrokerAccount = apps.get_model('brokers', 'BrokerAccount')
    field = models.ForeignKey(
        BrokerAccount,
        on_delete=django.db.models.deletion.CASCADE,
        related_name='connections',
        null=True,
        blank=True,
    )
    field.set_attributes_from_name('broker_account')
    schema_editor.add_field(BrokerConnection, field)


def ensure_broker_connection_index(apps, schema_editor):
    """Create the account/status index only when it is absent."""
    table = 'brokers_brokerconnection'
    name = 'brokers_bro_account__f3e4a0_idx'
    if name in _existing_db_objects(schema_editor.connection, table):
        return
    Model = apps.get_model('brokers', 'BrokerConnection')
    schema_editor.add_index(
        Model,
        models.Index(fields=['broker_account', 'status'], name=name),
    )


def ensure_order_index(apps, schema_editor):
    """Create the account/status order index only when it is absent."""
    table = 'brokers_order'
    name = 'brokers_ord_account__d1f2c7_idx'
    if name in _existing_db_objects(schema_editor.connection, table):
        return
    Model = apps.get_model('brokers', 'Order')
    schema_editor.add_index(
        Model,
        models.Index(fields=['account', 'status'], name=name),
    )


def repair_duplicate_client_order_ids(apps, schema_editor):
    Order = apps.get_model('brokers', 'Order')
    seen = set()
    queryset = Order.objects.exclude(client_order_id='').order_by(
        'user_id', 'account_id', 'client_order_id', 'id'
    )
    for order in queryset.iterator():
        key = (order.user_id, order.account_id, order.client_order_id)
        if key not in seen:
            seen.add(key)
            continue
        order.client_order_id = f'{order.client_order_id}-legacy-{order.pk}'
        order.save(update_fields=['client_order_id'])


def ensure_broker_connection_uniqueness(apps, schema_editor):
    """Ensure the conditional unique constraint exists without duplicating it."""
    table = 'brokers_brokerconnection'
    name = 'unique_broker_connection_per_account'
    if name in _existing_db_objects(schema_editor.connection, table):
        return
    Model = apps.get_model('brokers', 'BrokerConnection')
    constraint = models.UniqueConstraint(
        condition=Q(broker_account__isnull=False),
        fields=('broker_account',),
        name=name,
    )
    schema_editor.add_constraint(Model, constraint)


def ensure_order_idempotency_constraint(apps, schema_editor):
    """Ensure the conditional order idempotency constraint exists once."""
    table = 'brokers_order'
    name = 'unique_client_order_id_per_account'
    if name in _existing_db_objects(schema_editor.connection, table):
        return
    Model = apps.get_model('brokers', 'Order')
    constraint = models.UniqueConstraint(
        condition=~Q(client_order_id=''),
        fields=('user', 'account', 'client_order_id'),
        name=name,
    )
    schema_editor.add_constraint(Model, constraint)


class Migration(migrations.Migration):
    dependencies = [
        ('brokers', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    ensure_broker_account_column,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='brokerconnection',
                    name='broker_account',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='connections',
                        to='brokers.brokeraccount',
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    ensure_broker_connection_index,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name='brokerconnection',
                    index=models.Index(
                        fields=['broker_account', 'status'],
                        name='brokers_bro_account__f3e4a0_idx',
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            repair_duplicate_client_order_ids,
            migrations.RunPython.noop,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    ensure_order_index,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name='order',
                    index=models.Index(
                        fields=['account', 'status'],
                        name='brokers_ord_account__d1f2c7_idx',
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    ensure_broker_connection_uniqueness,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name='brokerconnection',
                    constraint=models.UniqueConstraint(
                        condition=Q(broker_account__isnull=False),
                        fields=('broker_account',),
                        name='unique_broker_connection_per_account',
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    ensure_order_idempotency_constraint,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name='order',
                    constraint=models.UniqueConstraint(
                        condition=~Q(client_order_id=''),
                        fields=('user', 'account', 'client_order_id'),
                        name='unique_client_order_id_per_account',
                    ),
                ],
            ),
        ),
    ]
