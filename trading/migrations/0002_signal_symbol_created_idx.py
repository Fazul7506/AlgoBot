from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="signal",
            index=models.Index(
                fields=["symbol", "-created_at"],
                name="signal_symbol_created_idx",
            ),
        ),
    ]
