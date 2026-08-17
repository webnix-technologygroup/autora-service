import os
import subprocess
import sys
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from service.models import NotificationLog, Order
from service.notifications import MAX_ATTEMPTS, claim, deliver, process_one, sanitize_error
from service.policies import scope_orders

from .base import MotorCase


class PermissionAndStatusTests(MotorCase):
    def test_manager_group_without_granular_permission_has_no_full_scope(self):
        manager = self.employee("manager", "Менеджеры")
        self.assertFalse(scope_orders(manager).filter(pk=self.order.pk).exists())

    def test_mechanic_assigned_can_view(self):
        mechanic = self.employee("assigned")
        self.order.assigned_to = mechanic
        self.order.save()
        self.assertTrue(scope_orders(mechanic).filter(pk=self.order.pk).exists())

    def test_mechanic_other_cannot_view(self):
        mechanic = self.employee("other")
        self.assertFalse(scope_orders(mechanic).filter(pk=self.order.pk).exists())

    def test_unassigned_permission(self):
        mechanic = self.employee("unassigned", permissions=("view_unassigned_orders",))
        self.assertTrue(scope_orders(mechanic).filter(pk=self.order.pk).exists())

    def test_superuser_full_scope(self):
        user = User.objects.create_superuser("root", "root@example.invalid", "test-password")
        self.assertTrue(scope_orders(user).filter(pk=self.order.pk).exists())

    def test_ui_permission_flags_match_permissions(self):
        user = self.employee("finance", "Менеджеры", ("view_all_orders", "manage_finance"))
        self.client.force_login(user)
        response = self.client.get(reverse("staff_order_detail", args=[self.order.pk]))
        self.assertTrue(response.context["can_manage_finance"])
        self.assertFalse(response.context["can_schedule"])
        self.assertFalse(response.context["can_manage_links"])

    def test_each_granular_flag(self):
        user = self.employee(
            "allflags",
            "Менеджеры",
            ("view_all_orders", "manage_schedule", "manage_finance", "manage_links", "retry_notifications"),
        )
        self.client.force_login(user)
        context = self.client.get(reverse("staff_order_detail", args=[self.order.pk])).context
        for flag in ("can_schedule", "can_manage_finance", "can_assign", "can_manage_links", "can_retry"):
            self.assertTrue(context[flag])

    def test_stale_status_does_not_500_or_modify(self):
        user = self.employee("status", "Менеджеры", ("view_all_orders",))
        self.client.force_login(user)
        response = self.client.post(
            reverse("change_status", args=[self.order.pk]),
            {
                "status": "pending",
                "expected_status": "accepted",
                "public_message": "",
                "internal_message": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.NEW)

    def test_invalid_transition_does_not_modify(self):
        user = self.employee("invalid", "Менеджеры", ("view_all_orders",))
        self.client.force_login(user)
        self.client.post(
            reverse("change_status", args=[self.order.pk]),
            {"status": "repair", "expected_status": "new", "public_message": "", "internal_message": ""},
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.NEW)

    def test_terminal_order_mutation_denied(self):
        user = self.employee("terminal", "Менеджеры", ("view_all_orders",))
        self.order.status = Order.Status.DONE
        self.order.save()
        self.client.force_login(user)
        self.assertEqual(
            self.client.post(reverse("change_status", args=[self.order.pk]), {}).status_code, 403
        )

    def test_invalid_filters_do_not_500(self):
        user = self.employee("filters", "Менеджеры", ("view_all_orders",))
        self.client.force_login(user)
        response = self.client.get(
            reverse("staff_orders"),
            {
                "status": "invalid",
                "service": "x",
                "assigned": "-1",
                "date": "bad",
                "sort": "customer__phone",
                "view": "all-everything",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_invalid_filters_do_not_expand_scope(self):
        mechanic = self.employee("scoped")
        self.order.assigned_to = mechanic
        self.order.save()
        other = Order.objects.create(
            number=Order.new_number(),
            customer=self.customer,
            vehicle=self.vehicle,
            service=self.service,
            service_name=self.service.name,
            service_price_from=self.service.price_from,
            problem="other",
            desired_date=self.order.desired_date,
        )
        self.client.force_login(mechanic)
        response = self.client.get(reverse("staff_orders"), {"status": "invalid"})
        self.assertContains(response, self.order.number)
        self.assertNotContains(response, other.number)


@override_settings(
    TELEGRAM_BOT_TOKEN="telegram-secret-token-value",
    TELEGRAM_CHAT_ID="chat",
    CLIENT_TOKEN_ENCRYPTION_KEYS=["encryption-secret-value"],
    EMAIL_HOST_PASSWORD="smtp-secret-value",
)
class NotificationTests(MotorCase):
    def notification(self, channel=NotificationLog.Channel.TELEGRAM):
        return NotificationLog.objects.create(
            order=self.order,
            channel=channel,
            event_type="demo",
            dedupe_key=f"{self.order.pk}:{channel}:{NotificationLog.objects.count()}",
        )

    @patch("service.notifications.urllib.request.urlopen")
    def test_correct_telegram_url(self, urlopen):
        response = MagicMock(status=200)
        urlopen.return_value.__enter__.return_value = response
        deliver(self.notification())
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url, "https://api.telegram.org/bottelegram-secret-token-value/sendMessage"
        )

    @patch("service.notifications.urllib.request.urlopen")
    def test_utf8_payload(self, urlopen):
        urlopen.return_value.__enter__.return_value = MagicMock(status=200)
        deliver(self.notification())
        payload = urlopen.call_args.args[0].data.decode("utf-8")
        self.assertIn("Заказ", payload)

    @patch("service.notifications.EmailMultiAlternatives.send")
    @override_settings(EMAIL_ENABLED=True)
    def test_email_mocked_success(self, send):
        deliver(self.notification(NotificationLog.Channel.EMAIL))
        send.assert_called_once()

    @patch("service.notifications.urllib.request.urlopen")
    def test_telegram_mocked_success(self, urlopen):
        urlopen.return_value.__enter__.return_value = MagicMock(status=200)
        deliver(self.notification())
        self.assertTrue(urlopen.called)

    @patch("service.notifications.deliver", side_effect=OSError("temporary"))
    def test_transient_failure_returns_pending(self, _):
        item = self.notification()
        process_one("worker")
        item.refresh_from_db()
        self.assertEqual(item.status, NotificationLog.Status.PENDING)

    @patch("service.notifications.deliver", side_effect=OSError("permanent"))
    def test_permanent_failure(self, _):
        item = self.notification()
        item.attempts = MAX_ATTEMPTS - 1
        item.save()
        process_one("worker")
        item.refresh_from_db()
        self.assertEqual(item.status, NotificationLog.Status.FAILED)

    def test_stale_processing_reclaim(self):
        item = self.notification()
        item.status = NotificationLog.Status.PROCESSING
        item.locked_at = timezone.now() - timedelta(minutes=20)
        item.save()
        self.assertEqual(claim("worker"), item.pk)

    def test_sanitizer_hides_all_secrets(self):
        text = sanitize_error(
            "telegram-secret-token-value smtp-secret-value encryption-secret-value https://secret.invalid/ abcdefghijklmnopqrstuvwxyzABCDEFG123456"
        )
        self.assertNotIn("telegram-secret", text)
        self.assertNotIn("smtp-secret", text)
        self.assertNotIn("encryption-secret", text)
        self.assertNotIn("https://", text)

    def test_sqlite_claim_compatibility(self):
        item = self.notification()
        self.assertEqual(claim("sqlite-worker"), item.pk)


class SettingsSubprocessTests(MotorCase):
    def run_settings(self, **changes):
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.getcwd(),
            "DJANGO_ENV": "production",
            "DJANGO_DEBUG": "0",
            "DJANGO_SECRET_KEY": "ci-strong-94e7136ac85f4d0d964f51e94a53b9b8294d7b18f9f45e6e",
            "DJANGO_ALLOWED_HOSTS": "motor.test",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://motor.test",
            "PUBLIC_BASE_URL": "https://motor.test",
            "POSTGRES_DB": "motor",
            "POSTGRES_USER": "motor",
            "POSTGRES_PASSWORD": "ci-db-94e7136ac85f4d0d964f",
            "POSTGRES_HOST": "db",
            "REDIS_URL": "redis://redis:6379/1",
            "CLIENT_TOKEN_ENCRYPTION_KEYS": "ci-key-94e7136ac85f4d0d964f51e94a53",
            "EMAIL_ENABLED": "0",
            "SECURE_SSL_REDIRECT": "1",
        }
        for key, value in changes.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            [sys.executable, "-c", "import config.settings"], env=env, capture_output=True, text=True
        )

    def test_valid_development(self):
        result = self.run_settings(
            DJANGO_ENV="development",
            DJANGO_SECRET_KEY=None,
            POSTGRES_DB=None,
            POSTGRES_USER=None,
            POSTGRES_PASSWORD=None,
            POSTGRES_HOST=None,
            REDIS_URL=None,
            DJANGO_CSRF_TRUSTED_ORIGINS=None,
            PUBLIC_BASE_URL="http://127.0.0.1:8000",
            DJANGO_ALLOWED_HOSTS="localhost",
            SECURE_SSL_REDIRECT="0",
        )
        self.assertEqual(result.returncode, 0)

    def test_unknown_environment(self):
        self.assertNotEqual(self.run_settings(DJANGO_ENV="staging").returncode, 0)

    def test_production_missing_secret(self):
        self.assertNotEqual(self.run_settings(DJANGO_SECRET_KEY=None).returncode, 0)

    def test_short_secret(self):
        self.assertNotEqual(self.run_settings(DJANGO_SECRET_KEY="short").returncode, 0)

    def test_missing_redis(self):
        self.assertNotEqual(self.run_settings(REDIS_URL=None).returncode, 0)

    def test_http_production_url(self):
        self.assertNotEqual(self.run_settings(PUBLIC_BASE_URL="http://motor.test").returncode, 0)

    def test_placeholder_db_password(self):
        self.assertNotEqual(self.run_settings(POSTGRES_PASSWORD="change-me-now-please").returncode, 0)

    def test_placeholder_encryption_key(self):
        self.assertNotEqual(
            self.run_settings(CLIENT_TOKEN_ENCRYPTION_KEYS="replace-me-encryption-key-value").returncode, 0
        )

    def test_development_key_in_production(self):
        self.assertNotEqual(
            self.run_settings(
                CLIENT_TOKEN_ENCRYPTION_KEYS="local-development-encryption-key-change-me"
            ).returncode,
            0,
        )

    def test_placeholder_email_password(self):
        self.assertNotEqual(
            self.run_settings(
                EMAIL_ENABLED="1",
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="smtp.motor.test",
                DEFAULT_FROM_EMAIL="service@motor.test",
                EMAIL_HOST_PASSWORD="set-me-password",
            ).returncode,
            0,
        )

    def test_valid_synthetic_production(self):
        self.assertEqual(self.run_settings().returncode, 0)
