from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

class Migration(migrations.Migration):
    dependencies = [("service", "0002_portfolio_upgrade"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField("clientaccess", "token_ciphertext", models.TextField(blank=True)),
        migrations.AddField("order", "confirmed_start_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("order", "confirmed_end_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("order", "booking_confirmed_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("order", "confirmed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="confirmed_orders", to=settings.AUTH_USER_MODEL)),
        migrations.AddField("order", "estimate_approval_recorded_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("order", "estimate_approval_note", models.CharField(blank=True, max_length=500)),
        migrations.AddField("order", "estimate_approval_recorded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="estimate_approvals", to=settings.AUTH_USER_MODEL)),
        migrations.AddField("notificationlog", "next_attempt_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
        migrations.AddField("notificationlog", "locked_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("notificationlog", "failed_permanently_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("submission", "session_key", models.CharField(db_index=True, default="legacy", max_length=40), preserve_default=False),
        migrations.AddField("submission", "expires_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
        migrations.AlterModelOptions("order", options={"ordering": ["-created_at"], "permissions": [("view_all_orders", "Может видеть все заказы"), ("view_unassigned_orders", "Может видеть неназначенные заказы"), ("manage_schedule", "Может подтверждать расписание"), ("manage_finance", "Может управлять сметой"), ("manage_links", "Может перевыпускать клиентские ссылки"), ("retry_notifications", "Может повторять уведомления")]}),
    ]
