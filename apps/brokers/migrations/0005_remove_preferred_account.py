from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('brokers', '0004_unique_preferred_account_per_user'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='brokeraccount',
            name='unique_preferred_broker_account_per_user',
        ),
        migrations.RemoveIndex(
            model_name='brokeraccount',
            name='brokers_bro_broker__f29040_idx',
        ),
        migrations.RemoveField(
            model_name='brokeraccount',
            name='is_preferred',
        ),
    ]
