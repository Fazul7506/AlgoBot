from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(
            name="KillSwitchEvent",
        ),
    ]
