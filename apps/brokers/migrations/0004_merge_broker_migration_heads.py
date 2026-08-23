from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0003_alter_broker_broker_type_alter_broker_status"),
        ("brokers", "0003_remove_legacy_broker_tables"),
    ]

    operations = []
