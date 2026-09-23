from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="subscription",
            name="stripe_price_id",
        ),
        migrations.AddField(
            model_name="subscription",
            name="provider",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="subscription",
            name="provider_subscription_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="subscription",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="cancellation_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(model_name="invoice", name="currency", field=models.CharField(default="kes", max_length=10)),
        migrations.AlterField(model_name="payment", name="currency", field=models.CharField(default="kes", max_length=10)),
        migrations.AlterField(
            model_name="subscription",
            name="currency",
            field=models.CharField(default="kes", max_length=10),
        ),
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("PROCESSING", "Processing"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                    ("CANCELLED", "Cancelled"),
                    ("REFUNDED", "Refunded"),
                ],
                db_index=True,
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.CheckConstraint(
                condition=Q(amount_cents__gte=0),
                name="core_invoice_amount_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=Q(amount_cents__gte=0),
                name="core_payment_amount_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.CheckConstraint(
                condition=Q(price_cents__gte=0),
                name="core_subscription_price_nonnegative",
            ),
        ),
        migrations.CreateModel(
            name="PaymentWebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=32)),
                ("event_key", models.CharField(max_length=255)),
                ("payload_hash", models.CharField(max_length=64)),
                ("external_id", models.CharField(blank=True, max_length=255)),
                ("received_status", models.CharField(blank=True, max_length=32)),
                ("processed_status", models.CharField(blank=True, max_length=32)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, max_length=500)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("provider", "event_key"),
                        name="core_webhook_provider_event_uniq",
                    )
                ],
                "indexes": [
                    models.Index(fields=("provider", "external_id"), name="core_wh_provider_ext_idx"),
                    models.Index(fields=("provider", "-received_at"), name="core_wh_provider_rcv_idx"),
                ],
            },
        ),
    ]
