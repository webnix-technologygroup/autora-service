import base64
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from service.forms import BookingForm
from service.links import issue_link
from service.models import Order, OrderPhoto

from .base import MotorCase

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class BookingErrorSummaryTests(MotorCase):
    def valid_payload(self):
        desired_date = timezone.localdate() + timedelta(days=2)
        while desired_date.weekday() == 6:
            desired_date += timedelta(days=1)
        response = self.client.get(reverse("home"))
        submission_key = response.context["form"].initial["submission_key"]
        return {
            "name": "Новый клиент",
            "phone": "+380671234567",
            "email": "new@example.invalid",
            "make": "Ford",
            "model": "Focus",
            "year": "2020",
            "plate": "AA1111AA",
            "vin": "",
            "service": str(self.service.pk),
            "desired_date": str(desired_date),
            "desired_time": "",
            "problem": "Диагностика",
            "consent": "on",
            "website": "",
            "submission_key": submission_key,
        }

    def invalid_name_response(self):
        payload = self.valid_payload()
        payload["name"] = ""
        return self.client.post(reverse("home"), payload)

    def test_field_only_error_creates_summary(self):
        response = self.invalid_name_response()
        self.assertContains(response, "data-error-summary")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, 'tabindex="-1"')
        self.assertContains(response, "Проверьте отмеченные поля")

    def test_invalid_field_receives_aria_invalid(self):
        response = self.invalid_name_response()
        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'aria-invalid="true"')

    def test_aria_describedby_points_to_existing_unique_id(self):
        html = self.invalid_name_response().content.decode()
        self.assertIn('aria-describedby="error-name"', html)
        self.assertEqual(html.count('id="error-name"'), 1)

    def test_multiple_field_errors_do_not_duplicate_ids(self):
        payload = self.valid_payload()
        with patch.object(
            BookingForm,
            "clean_name",
            side_effect=ValidationError(["Первая ошибка", "Вторая ошибка"]),
        ):
            response = self.client.post(reverse("home"), payload)
        html = response.content.decode()
        self.assertEqual(html.count('id="error-name"'), 1)
        self.assertContains(response, "Первая ошибка")
        self.assertContains(response, "Вторая ошибка")


class PrivatePhotoCrossOrderTests(MotorCase):
    def test_client_cannot_read_photo_from_another_order(self):
        other_order = Order.objects.create(
            number=Order.new_number(),
            customer=self.customer,
            vehicle=self.vehicle,
            service=self.service,
            service_name=self.service.name,
            service_price_from=Decimal("900.00"),
            problem="Другой заказ",
            desired_date=self.order.desired_date,
        )
        with tempfile.TemporaryDirectory() as media_root:
            with self.settings(MEDIA_ROOT=media_root):
                photo_a = OrderPhoto(
                    order=self.order,
                    original_name="order-a.png",
                    content_type="image/png",
                    size=len(PNG_1X1),
                )
                photo_a.image.save(
                    "order-a.png",
                    ContentFile(PNG_1X1),
                    save=True,
                )
                photo_b = OrderPhoto(
                    order=other_order,
                    original_name="order-b.png",
                    content_type="image/png",
                    size=len(PNG_1X1),
                )
                photo_b.image.save(
                    "order-b.png",
                    ContentFile(PNG_1X1),
                    save=True,
                )

                token = issue_link(self.order)
                self.client.get(
                    reverse(
                        "client_exchange",
                        args=[self.order.public_id, token],
                    )
                )
                denied = self.client.get(reverse("private_photo", args=[photo_b.pk]))
                allowed = self.client.get(reverse("private_photo", args=[photo_a.pk]))

                self.assertEqual(denied.status_code, 404)
                self.assertEqual(allowed.status_code, 200)
                self.assertEqual(allowed["Content-Type"], "image/png")
                allowed.close()
