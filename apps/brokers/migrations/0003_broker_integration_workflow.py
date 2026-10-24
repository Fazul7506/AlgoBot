# Generated for persistent broker integration requests and runs.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("brokers", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BrokerIntegrationRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider_name", models.CharField(db_index=True, max_length=120)),
                ("provider_website", models.URLField(blank=True)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("use_case", models.TextField()),
                ("desired_capabilities", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("in_progress", "In Progress"), ("completed", "Completed"), ("rejected", "Rejected")], db_index=True, default="pending", max_length=20)),
                ("linked_pr_url", models.URLField(blank=True)),
                ("team_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="broker_integration_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="BrokerIntegrationRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider_name", models.CharField(db_index=True, max_length=120)),
                ("provider_slug", models.SlugField(db_index=True, max_length=120)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("generating", "Generating"), ("pr_open", "PR Open"), ("validating", "Validating"), ("failed", "Failed"), ("merged", "Merged")], db_index=True, default="queued", max_length=20)),
                ("pull_request_number", models.PositiveIntegerField(blank=True, null=True)),
                ("pull_request_url", models.URLField(blank=True)),
                ("head_sha", models.CharField(blank=True, max_length=64)),
                ("validation_results", models.JSONField(blank=True, default=dict)),
                ("requested_enhancements", models.JSONField(blank=True, default=list)),
                ("failure_detail", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="broker_integration_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
