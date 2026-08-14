from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):
    dependencies = [("developer", "0001_initial")]
    operations = [
        migrations.AddField(model_name="apikey", name="created_at", field=models.DateTimeField(auto_now_add=True, null=True)),
        migrations.AddField(model_name="apikey", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.AddField(model_name="webhook", name="created_at", field=models.DateTimeField(auto_now_add=True, null=True)),
        migrations.AddField(model_name="webhook", name="updated_at", field=models.DateTimeField(auto_now=True)),
        migrations.CreateModel(name="APIUsageEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("method", models.CharField(max_length=12)), ("path", models.CharField(max_length=500)),
            ("status_code", models.PositiveIntegerField(default=200)), ("latency_ms", models.FloatField(default=0)),
            ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ("api_key", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="usage_events", to="developer.apikey")),
            ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="developer_api_usage", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="RateLimitEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("identity", models.CharField(db_index=True, max_length=255)), ("path", models.CharField(max_length=500)),
            ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ("api_key", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rate_limit_events", to="developer.apikey")),
        ]),
        migrations.CreateModel(name="WebhookDelivery", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("event", models.CharField(max_length=120)), ("payload", models.JSONField(blank=True, default=dict)),
            ("status", models.CharField(default="pending", max_length=24)), ("attempts", models.PositiveIntegerField(default=0)),
            ("response_status", models.PositiveIntegerField(blank=True, null=True)), ("response_body", models.TextField(blank=True)),
            ("last_error", models.TextField(blank=True)), ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
            ("delivered_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("webhook", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="developer.webhook")),
        ]),
    ]
