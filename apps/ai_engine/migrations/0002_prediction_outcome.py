from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("ai_engine", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="PredictionOutcome",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actual_direction", models.CharField(blank=True, max_length=32)),
                ("actual_return", models.FloatField(default=0)),
                ("correct", models.BooleanField(db_index=True, null=True)),
                ("horizon_candles", models.PositiveIntegerField(default=1)),
                ("resolved_at", models.DateTimeField(db_index=True, null=True, blank=True)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("prediction", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="outcome", to="ai_engine.prediction")),
            ],
            options={"ordering": ["-resolved_at"], "indexes": [models.Index(fields=["correct", "resolved_at"], name="ai_engine_po_correct_resolved_idx")]},
        ),
    ]
