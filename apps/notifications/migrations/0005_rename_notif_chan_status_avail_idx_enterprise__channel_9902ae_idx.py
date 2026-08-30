from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("enterprise_notifications", "0004_telegram_reliability"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="notification",
            old_name="notif_chan_status_avail_idx",
            new_name="enterprise__channel_9902ae_idx",
        ),
    ]
