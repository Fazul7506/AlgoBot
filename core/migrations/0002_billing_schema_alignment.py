# Generated manually to align the billing models with the billing service.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="invoice",
            name="external_id",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments",
                to="core.invoice",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="external_id",
            field=models.CharField(blank=True, db_index=True, max_length=255, null=True, unique=True),
        ),
    ]
