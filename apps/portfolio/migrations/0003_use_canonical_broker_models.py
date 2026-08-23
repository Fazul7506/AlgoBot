from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("portfolio", "0002_alter_portfolioaccount_unique_together_and_more"),
        ("brokers", "0004_merge_broker_migration_heads"),
    ]

    operations = [
        migrations.AlterField(
            model_name="portfolioaccount",
            name="broker",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="portfolio_accounts",
                to="brokers.broker",
            ),
        ),
        migrations.AlterField(
            model_name="portfolioaccount",
            name="broker_account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="portfolio_links",
                to="brokers.brokeraccount",
            ),
        ),
    ]
