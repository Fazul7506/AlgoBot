from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [("notifications", "0003_rename_notifications_user_prov_status_idx_enterprise__user_id_72de89_idx")]

    operations = [
        migrations.AddField(model_name="notification", name="attempts", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="notification", name="available_at", field=models.DateTimeField(null=True, blank=True, db_index=True)),
        migrations.AddField(model_name="notification", name="last_error", field=models.TextField(blank=True)),
        migrations.AddField(model_name="notification", name="sent_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="notification", name="telegram_message_id", field=models.CharField(max_length=64, blank=True)),
        migrations.AddField(model_name="notification", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(model_name="notification", name="idempotency_key", field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        migrations.CreateModel(name="TelegramUpdate", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("update_id", models.BigIntegerField(unique=True)),
            ("received_at", models.DateTimeField(auto_now_add=True)),
            ("processed_at", models.DateTimeField(null=True, blank=True)),
        ], options={"ordering": ["-received_at"]}),
        migrations.CreateModel(name="TelegramRuntimeState", fields=[
            ("singleton", models.PositiveSmallIntegerField(primary_key=True, serialize=False, default=1)),
            ("mode", models.CharField(max_length=16, default="webhook")),
            ("status", models.CharField(max_length=24, default="starting")),
            ("started_at", models.DateTimeField(null=True, blank=True)),
            ("heartbeat_at", models.DateTimeField(null=True, blank=True)),
            ("last_success_at", models.DateTimeField(null=True, blank=True)),
            ("last_update_at", models.DateTimeField(null=True, blank=True)),
            ("last_delivery_at", models.DateTimeField(null=True, blank=True)),
            ("consecutive_failures", models.PositiveIntegerField(default=0)),
            ("reconnect_count", models.PositiveIntegerField(default=0)),
            ("last_error", models.TextField(blank=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["channel", "status", "available_at"], name="notif_chan_status_avail_idx")),
    ]
