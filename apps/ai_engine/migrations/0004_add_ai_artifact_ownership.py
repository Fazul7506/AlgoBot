from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai_engine", "0003_rename_ai_engine_po_correct_resolved_idx_ai_engine_p_correct_6bba0a_idx"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="prediction",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="ai_predictions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="trainingjob",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="ai_training_jobs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="airecommendation",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="ai_recommendations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="marketregime",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="ai_market_regimes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="anomalyevent",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="ai_anomalies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="prediction",
            index=models.Index(fields=["user", "symbol", "timeframe", "-created_at"], name="ai_engine_pr_user_id_2c6a2f_idx"),
        ),
        migrations.AddIndex(
            model_name="trainingjob",
            index=models.Index(fields=["user", "status", "-started_at"], name="ai_engine_tr_user_id_7fdb5a_idx"),
        ),
        migrations.AddIndex(
            model_name="airecommendation",
            index=models.Index(fields=["user", "symbol", "-timestamp"], name="ai_engine_ar_user_id_0a5f7d_idx"),
        ),
        migrations.AddIndex(
            model_name="marketregime",
            index=models.Index(fields=["user", "symbol", "-timestamp"], name="ai_engine_mr_user_id_1b8e6c_idx"),
        ),
        migrations.AddIndex(
            model_name="anomalyevent",
            index=models.Index(fields=["user", "symbol", "-timestamp"], name="ai_engine_ae_user_id_3c9f2a_idx"),
        ),
    ]
