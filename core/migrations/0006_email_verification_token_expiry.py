from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_google_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="email_verification_token_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
