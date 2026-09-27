from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0008_authoritative_positions"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="position",
            options={"ordering": ["-broker_timestamp", "-id"]},
        ),
    ]
