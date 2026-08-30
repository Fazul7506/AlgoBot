from django.db import migrations, models
from django.db.models import Q


def normalize_preferred_accounts(apps, schema_editor):
    BrokerAccount = apps.get_model('brokers', 'BrokerAccount')
    user_ids = BrokerAccount.objects.filter(is_preferred=True).values_list('user_id', flat=True).distinct()
    for user_id in user_ids.iterator():
        preferred = list(BrokerAccount.objects.filter(user_id=user_id, is_preferred=True).order_by('pk'))
        if len(preferred) > 1:
            BrokerAccount.objects.filter(pk__in=[account.pk for account in preferred[1:]]).update(is_preferred=False)


class Migration(migrations.Migration):
    dependencies = [
        ('brokers', '0003_reconcile_account_status_index_names'),
    ]

    operations = [
        migrations.RunPython(normalize_preferred_accounts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='brokeraccount',
            constraint=models.UniqueConstraint(
                fields=['user'],
                condition=Q(is_preferred=True),
                name='unique_preferred_broker_account_per_user',
            ),
        ),
    ]
