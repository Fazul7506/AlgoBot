from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0002_dual_order_risk_assessment"),
    ]

    operations = [
        migrations.DeleteModel(
            name="KillSwitchEvent",
        ),
    ]
