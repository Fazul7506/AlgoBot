from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('execution', '0004_order_contract_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='submitted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='executed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
