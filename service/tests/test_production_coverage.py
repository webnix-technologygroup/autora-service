import io
import tempfile
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from service.estimates import add_item, approve_current, delete_item, set_manual_estimate
from service.files import MAX_BYTES, normalize_image
from service.forms import EstimateItemForm
from service.models import EstimateItem, NotificationLog, Order, OrderEvent, OrderPhoto
from service.security import client_ip
from service.validators import normalize_phone, validate_requested_datetime, validate_vin

from .base import MotorCase


class FileRegressionTests(MotorCase):
    def upload(self, image_format="JPEG", suffix=".jpg", size=(16, 12), exif=None):
        output = io.BytesIO()
        image = Image.new("RGB", size, "red")
        save_options = {"exif": exif} if exif is not None else {}
        image.save(output, format=image_format, **save_options)
        return SimpleUploadedFile(
            f"client{suffix}", output.getvalue(), content_type="application/octet-stream"
        )

    def test_valid_jpeg_png_and_webp_are_normalized(self):
        for image_format, suffix, mime in (
            ("JPEG", ".jpg", "image/jpeg"),
            ("PNG", ".png", "image/png"),
            ("WEBP", ".webp", "image/webp"),
        ):
            with self.subTest(image_format=image_format):
                normalized, content_type, original = normalize_image(self.upload(image_format, suffix))
                self.assertEqual(content_type, mime)
                self.assertEqual(original, f"client{suffix}")
                generated = Path(normalized.name)
                self.assertEqual(generated.suffix, suffix)
                self.assertEqual(len(generated.stem), 32)
                self.assertTrue(all(character in "0123456789abcdef" for character in generated.stem))
                with Image.open(normalized) as result:
                    self.assertEqual(result.format, image_format)

    def test_empty_oversized_invalid_and_mismatched_uploads_are_rejected(self):
        invalid = SimpleUploadedFile("broken.jpg", b"not-an-image")
        mismatch = self.upload("PNG", ".jpg")
        empty = SimpleUploadedFile("empty.jpg", b"")
        oversized = SimpleUploadedFile("large.jpg", b"x" * (MAX_BYTES + 1))
        for upload in (invalid, mismatch, empty, oversized):
            with self.subTest(name=upload.name), self.assertRaises(ValidationError):
                normalize_image(upload)

    def test_decompression_bomb_is_rejected(self):
        with patch("service.files.Image.open", side_effect=Image.DecompressionBombError("bomb")):
            with self.assertRaises(ValidationError):
                normalize_image(self.upload())

    def test_pixel_limit_is_rejected(self):
        with patch("service.files.MAX_PIXELS", 50):
            with self.assertRaises(ValidationError):
                normalize_image(self.upload(size=(20, 20)))

    def test_exif_orientation_is_applied_and_large_image_is_resized(self):
        exif = Image.Exif()
        exif[274] = 6
        normalized, _, _ = normalize_image(self.upload(size=(3000, 2), exif=exif))
        with Image.open(normalized) as result:
            self.assertEqual(result.size, (2, 2400))

    def test_photo_file_is_removed_after_model_delete(self):
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            photo = OrderPhoto.objects.create(
                order=self.order,
                image=ContentFile(b"image-bytes", name="orders/private/delete-me.jpg"),
                original_name="delete-me.jpg",
                content_type="image/jpeg",
                size=11,
            )
            path = Path(photo.image.path)
            self.assertTrue(path.exists())
            photo.delete()
            self.assertFalse(path.exists())


class SecurityAndValidatorRegressionTests(MotorCase):
    def test_client_ip_handles_proxy_remote_and_malformed_values(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1", REMOTE_ADDR="127.0.0.1")
        with override_settings(TRUST_PROXY_HEADERS=True):
            self.assertEqual(client_ip(request), "203.0.113.9")
        request = factory.get("/", HTTP_X_FORWARDED_FOR="bad", REMOTE_ADDR="198.51.100.7")
        with override_settings(TRUST_PROXY_HEADERS=True):
            self.assertEqual(client_ip(request), "198.51.100.7")
        request = factory.get("/", REMOTE_ADDR="not-an-ip")
        with override_settings(TRUST_PROXY_HEADERS=False):
            self.assertEqual(client_ip(request), "unknown")

    def test_phone_and_vin_validation(self):
        self.assertEqual(normalize_phone("00 380 (50) 123-45-67"), "+380501234567")
        self.assertEqual(normalize_phone("380501234567"), "+380501234567")
        with self.assertRaises(ValidationError):
            normalize_phone("123")
        self.assertEqual(validate_vin("1hgcm82633a004352"), "1HGCM82633A004352")
        self.assertEqual(validate_vin(""), "")
        with self.assertRaises(ValidationError):
            validate_vin("INVALID-I-O-Q")

    def test_requested_datetime_boundaries(self):
        today = timezone.localdate()
        with self.assertRaises(ValidationError):
            validate_requested_datetime(today - timedelta(days=1))
        with self.assertRaises(ValidationError):
            validate_requested_datetime(today + timedelta(days=181))
        sunday = today + timedelta(days=(6 - today.weekday()) % 7)
        with self.assertRaises(ValidationError):
            validate_requested_datetime(sunday)
        valid_day = today + timedelta(days=1)
        while valid_day.weekday() == 6:
            valid_day += timedelta(days=1)
        with self.assertRaises(ValidationError):
            validate_requested_datetime(valid_day, time(7, 59))
        validate_requested_datetime(valid_day, time(8, 0))


class AuthenticationRegressionTests(MotorCase):
    def test_anonymous_redirect_and_non_employee_denial(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, "/staff/login/?next=/staff/", fetch_redirect_response=False)
        user = self.employee("outsider")
        user.groups.clear()
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)

    def test_manager_only_permission_denial(self):
        mechanic = self.employee("mechanic")
        self.order.assigned_to = mechanic
        self.order.save(update_fields=["assigned_to"])
        self.client.force_login(mechanic)
        response = self.client.post(
            reverse("assign_order", args=[self.order.pk]), {"assigned_to": mechanic.pk}
        )
        self.assertEqual(response.status_code, 403)

    def test_failed_login_counter_and_429(self):
        self.employee("login-user")
        url = reverse("login")
        for _ in range(5):
            response = self.client.post(url, {"username": "login-user", "password": "wrong"})
            self.assertEqual(response.status_code, 200)
        key = "login:127.0.0.1:login-user"
        self.assertEqual(cache.get(key), 5)
        self.assertEqual(
            self.client.post(url, {"username": "login-user", "password": "wrong"}).status_code,
            429,
        )

    def test_successful_login_clears_counter(self):
        self.employee("successful")
        key = "login:127.0.0.1:successful"
        cache.set(key, 4, 900)
        response = self.client.post(
            reverse("login"),
            {"username": "successful", "password": "test-password"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(cache.get(key))


class EstimateRegressionTests(MotorCase):
    def item_form(self, name="Работа", quantity="2", unit_price="125.00"):
        form = EstimateItemForm(
            {
                "item_type": EstimateItem.ItemType.WORK,
                "name": name,
                "quantity": quantity,
                "unit_price": unit_price,
                "order_index": "1",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_add_and_delete_items_recalculate_and_audit(self):
        actor = self.employee("estimator", group="Менеджеры")
        item = add_item(self.order, self.item_form(), actor)
        self.order.refresh_from_db()
        self.assertEqual(self.order.estimate, Decimal("250.00"))
        self.assertFalse(self.order.estimate_approved)
        self.assertTrue(OrderEvent.objects.filter(order=self.order, kind=OrderEvent.Kind.PRICE).exists())
        self.assertEqual(delete_item(self.order, item, actor), Decimal("0.00"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.estimate, Decimal("0.00"))

    def test_terminal_orders_deny_item_and_manual_changes(self):
        actor = self.employee("terminal-estimator", group="Менеджеры")
        self.order.status = Order.Status.DONE
        self.order.save(update_fields=["status"])
        item = EstimateItem.objects.create(
            order=self.order,
            item_type=EstimateItem.ItemType.WORK,
            name="Existing",
            quantity=1,
            unit_price=10,
        )
        with self.assertRaises(PermissionDenied):
            add_item(self.order, self.item_form(), actor)
        with self.assertRaises(PermissionDenied):
            delete_item(self.order, item, actor)
        with self.assertRaises(PermissionDenied):
            set_manual_estimate(self.order.pk, Decimal("20"), "note", None, actor)

    def test_manual_amount_unchanged_change_and_item_precedence(self):
        actor = self.employee("manual-estimator", group="Менеджеры")
        self.order.estimate = Decimal("100.00")
        self.order.estimate_approved = True
        self.order.approved_estimate_amount = Decimal("100.00")
        self.order.save()
        unchanged = set_manual_estimate(self.order.pk, Decimal("100.00"), "same", None, actor)
        self.assertTrue(unchanged.estimate_approved)
        changed = set_manual_estimate(self.order.pk, Decimal("150.00"), "changed", Decimal("140"), actor)
        self.assertFalse(changed.estimate_approved)
        self.assertEqual(changed.estimate, Decimal("150.00"))
        EstimateItem.objects.create(
            order=self.order,
            item_type=EstimateItem.ItemType.PART,
            name="Part",
            quantity=2,
            unit_price=30,
        )
        with_items = set_manual_estimate(self.order.pk, Decimal("999.00"), "items win", None, actor)
        self.assertEqual(with_items.estimate, Decimal("60.00"))

    def test_approval_validation_idempotency_audit_and_notification(self):
        actor = self.employee("approver", group="Менеджеры")
        with self.assertRaises(ValidationError):
            approve_current(self.order.pk, 1, "phone", actor)
        self.order.status = Order.Status.AWAITING_APPROVAL
        self.order.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            approve_current(self.order.pk, 1, "phone", actor)
        Order.objects.filter(pk=self.order.pk).update(estimate=Decimal("-1.00"))
        with self.assertRaises(ValidationError):
            approve_current(self.order.pk, 1, "phone", actor)
        Order.objects.filter(pk=self.order.pk).update(estimate=Decimal("100.00"))
        with self.assertRaises(ValidationError):
            approve_current(self.order.pk, 99, "phone", actor)
        with patch("service.estimates.queue_on_commit") as queued:
            approved, created = approve_current(self.order.pk, 1, "phone", actor, "called")
        self.assertTrue(created)
        self.assertEqual(approved.estimate_approval_recorded_by, actor)
        queued.assert_called_once()
        self.assertTrue(
            OrderEvent.objects.filter(order=self.order, public_message__contains="согласована").exists()
        )
        duplicate, created = approve_current(self.order.pk, 1, "phone", actor)
        self.assertFalse(created)
        self.assertEqual(duplicate.pk, self.order.pk)


class StaffEndpointRegressionTests(MotorCase):
    permissions = (
        "view_all_orders",
        "manage_schedule",
        "manage_finance",
        "manage_links",
        "retry_notifications",
    )

    def setUp(self):
        super().setUp()
        self.manager = self.employee("manager", group="Менеджеры", permissions=self.permissions)
        self.worker = self.employee("assigned-worker")
        self.client.force_login(self.manager)

    def test_assignment_success_invalid_and_conflict(self):
        url = reverse("assign_order", args=[self.order.pk])
        with patch("service.staff_views.assign_worker") as assign:
            self.assertEqual(self.client.post(url, {"assigned_to": self.worker.pk}).status_code, 302)
            assign.assert_called_once_with(self.order.pk, self.worker, self.manager)
        with patch("service.staff_views.assign_worker", side_effect=ValidationError("conflict")):
            self.assertEqual(self.client.post(url, {"assigned_to": self.worker.pk}).status_code, 302)
        with patch("service.staff_views.assign_worker") as assign:
            self.client.post(url, {"assigned_to": "invalid"})
            assign.assert_not_called()

    def test_schedule_success_invalid_and_conflict(self):
        url = reverse("update_schedule", args=[self.order.pk])
        start = timezone.localtime(timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)
        end = start + timedelta(hours=2)
        data = {
            "confirmed_start_at": start.strftime("%Y-%m-%dT%H:%M"),
            "confirmed_end_at": end.strftime("%Y-%m-%dT%H:%M"),
            "reason": "planned",
        }
        with patch("service.staff_views.schedule_order") as schedule:
            self.client.post(url, data)
            schedule.assert_called_once()
        with patch("service.staff_views.schedule_order", side_effect=ValidationError("busy")):
            self.assertEqual(self.client.post(url, data).status_code, 302)
        with patch("service.staff_views.schedule_order") as schedule:
            self.client.post(url, {"confirmed_start_at": "bad"})
            schedule.assert_not_called()

    def test_price_and_estimate_item_endpoints(self):
        with patch("service.staff_views.set_manual_estimate") as setter:
            response = self.client.post(
                reverse("update_price", args=[self.order.pk]),
                {"estimate": "125.00", "estimate_note": "note", "final_price": ""},
            )
            self.assertEqual(response.status_code, 302)
            setter.assert_called_once()
        with patch("service.staff_views.set_manual_estimate") as setter:
            self.client.post(reverse("update_price", args=[self.order.pk]), {"estimate": "-1"})
            setter.assert_not_called()
        item_data = {
            "item_type": EstimateItem.ItemType.WORK,
            "name": "Diagnostics",
            "quantity": "1",
            "unit_price": "50",
            "order_index": "0",
        }
        with patch("service.staff_views.estimate_add_item") as adder:
            self.client.post(reverse("add_estimate_item", args=[self.order.pk]), item_data)
            adder.assert_called_once()
        with patch("service.staff_views.estimate_add_item") as adder:
            self.client.post(reverse("add_estimate_item", args=[self.order.pk]), {"name": ""})
            adder.assert_not_called()
        item = EstimateItem.objects.create(order=self.order, item_type="work", name="Delete", unit_price=1)
        with patch("service.staff_views.estimate_delete_item") as deleter:
            self.client.post(reverse("delete_estimate_item", args=[self.order.pk, item.pk]))
            deleter.assert_called_once()

    def test_comment_reissue_retry_and_manual_approval(self):
        self.client.post(reverse("add_comment", args=[self.order.pk]), {"text": "Internal note"})
        self.assertEqual(self.order.comments.get().text, "Internal note")
        with (
            patch("service.staff_views.issue_link", return_value="raw-token"),
            patch("service.staff_views.queue_on_commit") as queued,
        ):
            self.client.post(reverse("reissue_link", args=[self.order.pk]))
            queued.assert_called_once()
        session = self.client.session
        self.assertIn(f"new_link:{self.order.pk}", session)
        notification = NotificationLog.objects.create(
            order=self.order,
            channel=NotificationLog.Channel.EMAIL,
            event_type="test",
            status=NotificationLog.Status.FAILED,
            dedupe_key="retry-test",
            last_error="failed",
            failed_permanently_at=timezone.now(),
        )
        self.client.post(reverse("retry_notification", args=[self.order.pk, notification.pk]))
        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationLog.Status.PENDING)
        self.order.status = Order.Status.AWAITING_APPROVAL
        self.order.estimate = Decimal("100")
        self.order.save()
        approval_data = {"version": self.order.estimate_version, "method": "phone", "note": "confirmed"}
        with patch("service.staff_views.approve_current", return_value=(self.order, True)) as approve:
            self.client.post(reverse("record_manual_approval", args=[self.order.pk]), approval_data)
            approve.assert_called_once()
        with patch("service.staff_views.approve_current", side_effect=ValidationError("stale")):
            response = self.client.post(
                reverse("record_manual_approval", args=[self.order.pk]), approval_data
            )
            self.assertEqual(response.status_code, 302)

    def test_granular_permission_denials(self):
        limited = self.employee("limited-manager", group="Менеджеры", permissions=("view_all_orders",))
        self.client.force_login(limited)
        item = EstimateItem.objects.create(order=self.order, item_type="work", name="Protected", unit_price=1)
        notification = NotificationLog.objects.create(
            order=self.order,
            channel="email",
            event_type="protected",
            status=NotificationLog.Status.FAILED,
            dedupe_key="protected-retry",
        )
        protected = (
            ("update_schedule", [self.order.pk]),
            ("update_price", [self.order.pk]),
            ("add_estimate_item", [self.order.pk]),
            ("delete_estimate_item", [self.order.pk, item.pk]),
            ("record_manual_approval", [self.order.pk]),
            ("reissue_link", [self.order.pk]),
            ("retry_notification", [self.order.pk, notification.pk]),
        )
        for name, args in protected:
            with self.subTest(name=name):
                self.assertEqual(self.client.post(reverse(name, args=args), {}).status_code, 403)
