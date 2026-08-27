import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('execution', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='ReconciliationEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('open', 'Open'), ('reviewed', 'Reviewed')], db_index=True, default='open', max_length=16)),
                ('discrepancy_type', models.CharField(db_index=True, max_length=64)),
                ('broker_reference', models.CharField(blank=True, db_index=True, max_length=160)),
                ('symbol', models.CharField(blank=True, max_length=40)),
                ('summary', models.CharField(max_length=255)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('detected_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('broker_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reconciliation_events', to='brokers.brokeraccount')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reviewed_reconciliation_events', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reconciliation_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-detected_at']},
        ),
        migrations.AddIndex(model_name='reconciliationevent', index=models.Index(fields=['broker_account', 'status', '-detected_at'], name='execution_r_broker_a_5c5c9f_idx')),
        migrations.AddIndex(model_name='reconciliationevent', index=models.Index(fields=['user', 'status', '-detected_at'], name='execution_r_user_id_8fcb15_idx')),
    ]
