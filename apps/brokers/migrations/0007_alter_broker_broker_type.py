from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("brokers", "0006_remove_paper_broker")]
    operations = [
        migrations.AlterField(
            model_name="broker",
            name="broker_type",
            field=models.CharField(
                choices=[
                    ("deriv", "Deriv"),
                    ("binance", "Binance"),
                    ("bybit", "Bybit"),
                    ("oanda", "Oanda"),
                    ("interactive_brokers", "Interactive Brokers"),
                    ("metatrader_gateway", "Metatrader Gateway"),
                    ("dxtrade", "Dxtrade"),
                    ("ctrader", "Ctrader"),
                    ("alpaca", "Alpaca"),
                    ("forex_com", "Forex Com"),
                    ("pepperstone", "Pepperstone"),
                    ("ic_markets", "Ic Markets"),
                    ("exness", "Exness"),
                    ("mt5", "Mt5"),
                    ("mt4", "Mt4"),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
    ]
