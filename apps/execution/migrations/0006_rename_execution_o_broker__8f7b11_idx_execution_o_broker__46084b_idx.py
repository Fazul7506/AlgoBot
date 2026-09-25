from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('execution', '0005_order_execution_timestamps'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='order',
            new_name='execution_o_broker__46084b_idx',
            old_name='execution_o_broker__8f7b11_idx',
        ),
    ]
