# Generated for the durable Google OIDC identity relationship.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_remove_paper_trading"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GoogleIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="google", max_length=32)),
                ("subject", models.CharField(max_length=255)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="google_identities", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="googleidentity",
            constraint=models.UniqueConstraint(fields=("provider", "subject"), name="core_google_provider_subject_uniq"),
        ),
        migrations.AddConstraint(
            model_name="googleidentity",
            constraint=models.UniqueConstraint(fields=("user", "provider"), name="core_google_user_provider_uniq"),
        ),
        migrations.AddIndex(
            model_name="googleidentity",
            index=models.Index(fields=["user", "provider"], name="core_google_user_prov_idx"),
        ),
    ]
