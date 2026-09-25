from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('execution', '0003_rename_execution_r_broker_a_5c5c9f_idx_execution_r_broker__627b64_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='contract_type',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name='order',
            name='duration',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='duration_unit',
            field=models.CharField(blank=True, max_length=1),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['broker_account', 'contract_type'], name='execution_o_broker__8f7b11_idx'),
        ),
    ]
