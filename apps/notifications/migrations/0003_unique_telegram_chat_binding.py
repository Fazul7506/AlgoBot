from django.db import migrations, models
from django.db.models import Q


def remove_duplicate_telegram_bindings(apps, schema_editor):
    Connection = apps.get_model("enterprise_notifications", "NotificationChannelConnection")
    external_ids = (
        Connection.objects.filter(provider="telegram")
        .exclude(external_id="")
        .values_list("external_id", flat=True)
        .distinct()
    )
    for external_id in external_ids.iterator():
        rows = list(
            Connection.objects.filter(provider="telegram", external_id=external_id)
            .order_by("created_at", "id")
        )
        if len(rows) < 2:
            continue
        keeper = next((row for row in rows if row.status == "verified"), rows[0])
        for row in rows:
            if row.pk == keeper.pk:
                continue
            row.status = "revoked"
            row.external_id = ""
            row.verification_code_hash = ""
            row.verification_expires_at = None
            row.save(update_fields=["status", "external_id", "verification_code_hash", "verification_expires_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("enterprise_notifications", "0002_notificationchannelconnection"),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_telegram_bindings, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="notificationchannelconnection",
            constraint=models.UniqueConstraint(
                fields=("external_id",),
                condition=Q(provider="telegram") & ~Q(external_id=""),
                name="uniq_telegram_chat_binding",
            ),
        ),
    ]
