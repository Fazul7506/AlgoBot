from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('strategies', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='strategyconfiguration',
            name='criteria',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='strategyconfiguration',
            name='is_active',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddIndex(
            model_name='strategyconfiguration',
            index=models.Index(fields=['user', 'is_active'], name='strategies_u_active_idx'),
        ),
    ]
