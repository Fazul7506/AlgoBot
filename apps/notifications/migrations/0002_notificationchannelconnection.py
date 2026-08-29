from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("notifications","0001_initial")]
    operations=[migrations.CreateModel(name="NotificationChannelConnection",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("provider",models.CharField(choices=[("gmail","Gmail"),("telegram","Telegram")],db_index=True,max_length=24)),
        ("status",models.CharField(choices=[("pending","Pending"),("verified","Verified"),("revoked","Revoked"),("error","Error")],db_index=True,default="pending",max_length=24)),
        ("address",models.CharField(blank=True,max_length=320)),("external_id",models.CharField(blank=True,max_length=180)),
        ("access_token",models.TextField(blank=True)),("refresh_token",models.TextField(blank=True)),("token_expires_at",models.DateTimeField(blank=True,null=True)),
        ("verification_code_hash",models.CharField(blank=True,max_length=128)),("verification_expires_at",models.DateTimeField(blank=True,null=True)),
        ("metadata",models.JSONField(blank=True,default=dict)),("verified_at",models.DateTimeField(blank=True,null=True)),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
        ("user",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="notification_channel_connections",to="auth.user")),
    ]),migrations.AddConstraint(model_name="notificationchannelconnection",constraint=models.UniqueConstraint(fields=("user","provider"),name="uniq_notification_channel_provider")),migrations.AddIndex(model_name="notificationchannelconnection",index=models.Index(fields=["user","provider","status"],name="notifications_user_prov_status_idx"))]