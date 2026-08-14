from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("copy_trading", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CopyProvider",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("slug", models.SlugField(max_length=180)),
                ("status", models.CharField(default="active", max_length=32)),
                ("strategy", models.CharField(blank=True, max_length=160)),
                ("description", models.TextField(blank=True)),
                ("risk_score", models.FloatField(default=0)),
                ("return_pct", models.FloatField(default=0)),
                ("win_rate", models.FloatField(default=0)),
                ("max_drawdown_pct", models.FloatField(default=0)),
                ("followers_count", models.PositiveIntegerField(default=0)),
                ("min_allocation", models.DecimalField(decimal_places=2, default=1, max_digits=12)),
                ("max_allocation", models.DecimalField(decimal_places=2, default=1000, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="copy_providers", to="tenants.tenant")),
            ],
            options={"ordering": ["-return_pct", "-followers_count", "name"]},
        ),
        migrations.CreateModel(
            name="CopyFollower",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("active", "Active"), ("paused", "Paused"), ("stopped", "Stopped")], default="active", max_length=32)),
                ("allocation", models.DecimalField(decimal_places=2, default=1, max_digits=12)),
                ("allocation_mode", models.CharField(choices=[("fixed", "Fixed"), ("proportional", "Proportional")], default="fixed", max_length=32)),
                ("max_daily_loss_pct", models.DecimalField(decimal_places=2, default=3, max_digits=8)),
                ("max_drawdown_pct", models.DecimalField(decimal_places=2, default=5, max_digits=8)),
                ("max_trade_stake", models.DecimalField(decimal_places=2, default=10, max_digits=12)),
                ("max_concurrent_trades", models.PositiveIntegerField(default=3)),
                ("pause_on_loss_streak", models.PositiveIntegerField(default=3)),
                ("copy_multiplier", models.DecimalField(decimal_places=4, default=1, max_digits=8)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="followers_profiles", to="copy_trading.copyprovider")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="copy_followers", to="tenants.tenant")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="copy_followers", to="auth.user")),
            ],
        ),
        migrations.CreateModel(
            name="CopySubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("active", "Active"), ("paused", "Paused"), ("cancelled", "Cancelled")], default="active", max_length=32)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("follower", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="subscription", to="copy_trading.copyfollower")),
            ],
        ),
        migrations.CreateModel(
            name="CopyTrade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider_trade", models.CharField(blank=True, max_length=120)),
                ("symbol", models.CharField(max_length=80)),
                ("direction", models.CharField(max_length=20)),
                ("stake", models.DecimalField(decimal_places=4, default=0, max_digits=14)),
                ("source_stake", models.DecimalField(decimal_places=4, default=0, max_digits=14)),
                ("profit", models.DecimalField(decimal_places=4, default=0, max_digits=14)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("open", "Open"), ("closed", "Closed"), ("cancelled", "Cancelled")], default="pending", max_length=32)),
                ("rejection_reason", models.TextField(blank=True)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("follower", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trades", to="copy_trading.copyfollower")),
            ],
            options={"ordering": ["-opened_at", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="copyprovider",
            constraint=models.UniqueConstraint(fields=("tenant", "slug"), name="copy_provider_tenant_slug_uniq"),
        ),
        migrations.AddConstraint(
            model_name="copyfollower",
            constraint=models.UniqueConstraint(fields=("user", "tenant", "provider"), name="copy_follower_user_tenant_provider_uniq"),
        ),
    ]
