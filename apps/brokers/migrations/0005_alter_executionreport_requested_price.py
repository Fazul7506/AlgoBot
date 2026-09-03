from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('brokers', '0004_unique_preferred_account_per_user'),
    ]

    operations = [
        migrations.AlterField(
            model_name='executionreport',
            name='requested_price',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=20),
        ),
    ]
