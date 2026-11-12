from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0009_alter_position_options"),
        ("brokers", "0003_broker_integration_workflow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="brokeraccount",
            name="currency",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
    ]
