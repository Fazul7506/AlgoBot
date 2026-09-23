from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_billing_hardening"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="currency",
            field=models.CharField(default="usd", max_length=10),
        ),
        migrations.AlterField(
            model_name="referralreward",
            name="amount_credits",
            field=models.DecimalField(decimal_places=8, max_digits=20),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="referral_credits",
            field=models.DecimalField(decimal_places=8, default=0, max_digits=20),
        ),
    ]
