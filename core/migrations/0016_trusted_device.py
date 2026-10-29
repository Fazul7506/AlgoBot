from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0015_account_preferences"),
    ]
    operations = [
        migrations.CreateModel(
            name="TrustedDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Trusted browser", max_length=100)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trusted_devices", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-last_seen_at", "-created_at"]},
        ),
        migrations.AddIndex(
            model_name="trusteddevice",
            index=models.Index(fields=["user", "revoked_at"], name="core_trust_user_rev_idx"),
        ),
    ]
