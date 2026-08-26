from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('brokers', '0002_account_scoped_connections_and_order_idempotency'),
        ('execution', '0001_initial'),
        ('risk', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='riskassessment',
            name='trade',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='risk_assessments',
                to='execution.order',
            ),
        ),
        migrations.AddField(
            model_name='riskassessment',
            name='broker_trade',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='risk_assessments',
                to='brokers.order',
            ),
        ),
    ]
