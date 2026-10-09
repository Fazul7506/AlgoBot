from django.db import migrations


class Migration(migrations.Migration):
    """Join the Telegram binding and notification reliability migration branches."""

    dependencies = [
        ("enterprise_notifications", "0003_unique_telegram_chat_binding"),
        ("enterprise_notifications", "0004_telegram_reliability"),
    ]

    operations = []
