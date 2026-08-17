import uuid
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("service","0003_staff_operations")]
    operations=[
        migrations.AddField("clientaccess","encryption_key_version",models.PositiveSmallIntegerField(default=1)),
        migrations.AddField("clientaccess","session_version",models.UUIDField(default=uuid.uuid4)),
        migrations.AddField("order","estimate_version",models.PositiveIntegerField(default=1)),
        migrations.AddField("order","approved_estimate_amount",models.DecimalField(blank=True,decimal_places=2,max_digits=10,null=True)),
        migrations.AddField("order","estimate_approval_method",models.CharField(blank=True,max_length=40)),
        migrations.AddField("notificationlog","event_id",models.UUIDField(db_index=True,default=uuid.uuid4)),
        migrations.AddField("notificationlog","worker_id",models.CharField(blank=True,max_length=80)),
        migrations.AlterField("notificationlog","dedupe_key",models.CharField(max_length=160,unique=True)),
        migrations.AlterField("notificationlog","status",models.CharField(choices=[("pending","Ожидает"),("processing","Обрабатывается"),("sent","Отправлено"),("failed","Ошибка")],default="pending",max_length=12)),
        migrations.AddIndex("notificationlog",models.Index(fields=["status","next_attempt_at"],name="service_not_status_next_idx")),
        migrations.AddIndex("notificationlog",models.Index(fields=["status","locked_at"],name="service_not_status_lock_idx")),
    ]
