from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


def ensure_broker_account_column(apps, schema_editor):
    """Ensure broker_account_id exists without failing on schema drift."""
    connection = schema_editor.connection
    table = 'brokers_brokerconnection'
    cursor = connection.cursor()
    existing_columns = {
        column.name
        for column in connection.introspection.get_table_description(cursor, table)
    }

    if 'broker_account_id' in existing_columns:
        return

    quoted_table = schema_editor.quote_name(table)
    quoted_column = schema_editor.quote_name('broker_account_id')
    quoted_target = schema_editor.quote_name('brokers_brokeraccount')

    # PostgreSQL is the production database on Render.  The equivalent
    # nullable BIGINT foreign-key column is also valid for the supported
    # development databases used by this project.
    schema_editor.execute(
        f'ALTER TABLE {quoted_table} '
        f'ADD COLUMN {quoted_column} bigint NULL '
        f'REFERENCES {quoted_target} ("id") '
        f'ON DELETE CASCADE'
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
        migrations.AddIndex(
            model_name='brokerconnection',
            index=models.Index(
                fields=['broker_account', 'status'],
                name='brokers_bro_account__f3e4a0_idx',
            ),
        ),
        migrations.RunPython(
            repair_duplicate_client_order_ids,
            migrations.RunPython.noop,
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(
                fields=['account', 'status'],
                name='brokers_ord_account__d1f2c7_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='brokerconnection',
            constraint=models.UniqueConstraint(
                condition=Q(broker_account__isnull=False),
                fields=('broker_account',),
                name='unique_broker_connection_per_account',
            ),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.UniqueConstraint(
                condition=~Q(client_order_id=''),
                fields=('user', 'account', 'client_order_id'),
                name='unique_client_order_id_per_account',
            ),
        ),
    ]
