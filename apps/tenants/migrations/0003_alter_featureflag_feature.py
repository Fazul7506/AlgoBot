from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tenants", "0002_remove_paper_feature")]
    operations = [
        migrations.AlterField(
            model_name="featureflag",
            name="feature",
            field=models.CharField(
                choices=[
                    ("ai_engine", "Ai Engine"),
                    ("copy_trading", "Copy Trading"),
                    ("api_access", "Api Access"),
                    ("backtesting", "Backtesting"),
                    ("monitoring", "Monitoring"),
                    ("portfolio_analytics", "Portfolio Analytics"),
                    ("multi_broker", "Multi Broker"),
                    ("white_label", "White Label"),
                    ("custom_branding", "Custom Branding"),
                ],
                max_length=64,
            ),
        ),
    ]
