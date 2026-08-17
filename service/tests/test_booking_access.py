import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from service.links import issue_link
from service.models import Order, OrderEvent, OrderPhoto

from .base import MotorCase


class BookingTests(MotorCase):
    def payload(self, key):
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
            "desired_date": str(timezone.localdate() + timedelta(days=3)),
            "desired_time": "10:00",
            "problem": "Диагностика",
            "consent": "on",
            "website": "",
            "submission_key": key,
        }

    def key(self, client=None):
        response = (client or self.client).get(reverse("home"))
        return response.context["form"].initial["submission_key"]

    def test_successful_booking(self):
        response = self.client.post(reverse("home"), self.payload(self.key()))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 2)

    def test_duplicate_submission_returns_page(self):
        key = self.key()
        self.client.post(reverse("home"), self.payload(key))
        response = self.client.post(reverse("home"), self.payload(key))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Заявка уже отправлена")

    def test_duplicate_does_not_create_second_order(self):
        key = self.key()
        self.client.post(reverse("home"), self.payload(key))
        count = Order.objects.count()
        self.client.post(reverse("home"), self.payload(key))
        self.assertEqual(Order.objects.count(), count)

    def test_duplicate_has_no_none_url(self):
        key = self.key()
        self.client.post(reverse("home"), self.payload(key))
        response = self.client.post(reverse("home"), self.payload(key))
        self.assertNotContains(response, "/None/")

    def test_wrong_session_key(self):
        key = self.key()
        other = Client()
        other.get(reverse("home"))
        response = other.post(reverse("home"), self.payload(key))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)

    def test_expired_key(self):
        self.client.get(reverse("home"))
        session = self.client.session.session_key
        with patch("django.core.signing.time.time", return_value=1):
            key = signing.TimestampSigner(salt="booking").sign(session + ":nonce")
        response = self.client.post(reverse("home"), self.payload(key))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)

    def test_malformed_key(self):
        response = self.client.post(reverse("home"), self.payload("broken"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)

    def test_honeypot(self):
        data = self.payload(self.key())
        data["website"] = "spam"
        response = self.client.post(reverse("home"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)

    def test_upload_count(self):
        data = self.payload(self.key())
        data["photos"] = [SimpleUploadedFile(f"{i}.jpg", b"x", content_type="image/jpeg") for i in range(6)]
        response = self.client.post(reverse("home"), data)
        self.assertContains(response, "не более 5")

    def test_aggregate_upload_size(self):
        data = self.payload(self.key())
        data["photos"] = [
            SimpleUploadedFile("large.jpg", b"x" * (25 * 1024 * 1024 + 1), content_type="image/jpeg")
        ]
        response = self.client.post(reverse("home"), data)
        self.assertContains(response, "25 МБ")

    @patch("service.views.cache.get", return_value=10)
    def test_rate_limit_429(self, _):
        response = self.client.post(reverse("home"), self.payload("bad"))
        self.assertEqual(response.status_code, 429)


class ClientAccessTests(MotorCase):
    def test_valid_exchange(self):
        token = issue_link(self.order)
        response = self.client.get(reverse("client_exchange", args=[self.order.public_id, token]))
        self.assertRedirects(response, reverse("client_portal"))

    def test_wrong_token(self):
        self.assertEqual(
            self.client.get(reverse("client_exchange", args=[self.order.public_id, "wrong"])).status_code, 404
        )

    def test_wrong_public_id(self):
        token = issue_link(self.order)
        self.assertEqual(
            self.client.get(reverse("client_exchange", args=[uuid.uuid4(), token])).status_code, 404
        )

    def test_revoked_link(self):
        token = issue_link(self.order)
        self.order.access_links.update(revoked_at=timezone.now())
        self.assertEqual(
            self.client.get(reverse("client_exchange", args=[self.order.public_id, token])).status_code, 404
        )

    def test_expired_link(self):
        token = issue_link(self.order)
        self.order.access_links.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(
            self.client.get(reverse("client_exchange", args=[self.order.public_id, token])).status_code, 404
        )

    def test_session_invalidation(self):
        token = issue_link(self.order)
        self.client.get(reverse("client_exchange", args=[self.order.public_id, token]))
        self.order.access_links.update(revoked_at=timezone.now())
        self.assertRedirects(self.client.get(reverse("client_portal")), reverse("client_login"))

    def test_private_photo_idor(self):
        photo = OrderPhoto.objects.create(
            order=self.order,
            image="orders/private/missing.jpg",
            original_name="x.jpg",
            content_type="image/jpeg",
            size=1,
        )
        self.assertEqual(self.client.get(reverse("private_photo", args=[photo.pk])).status_code, 404)

    def test_missing_physical_photo_returns_404(self):
        manager = self.employee("manager", "Менеджеры", ("view_all_orders",))
        self.client.force_login(manager)
        photo = OrderPhoto.objects.create(
            order=self.order,
            image="orders/private/missing.jpg",
            original_name="x.jpg",
            content_type="image/jpeg",
            size=1,
        )
        self.assertEqual(self.client.get(reverse("private_photo", args=[photo.pk])).status_code, 404)


class ClientCabinetFlowTests(MotorCase):
    def test_success_page_establishes_client_session(self):
        token = issue_link(self.order)
        response = self.client.get(
            reverse("success", args=[self.order.public_id, token])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Заявка принята")
        self.assertContains(response, self.order.number)
        self.assertEqual(self.client.get(reverse("client_portal")).status_code, 200)

    def test_client_can_add_order_by_number_only(self):
        issue_link(self.order)
        response = self.client.post(
            reverse("client_login"),
            {"order_number": self.order.number.lower()},
        )
        self.assertRedirects(response, reverse("client_portal"))
        portal = self.client.get(reverse("client_portal"))
        self.assertContains(portal, self.order.number)
        self.assertContains(portal, self.order.service_name)
        self.assertNotContains(self.client.get(reverse("client_login")), 'name="phone"')

    def test_cabinet_keeps_multiple_orders_in_same_browser(self):
        second = Order.objects.create(
            number=Order.new_number(),
            customer=self.customer,
            vehicle=self.vehicle,
            service=self.service,
            service_name=self.service.name,
            service_price_from=self.service.price_from,
            problem="Повторная заявка",
            desired_date=timezone.localdate() + timedelta(days=4),
        )
        issue_link(self.order)
        issue_link(second)
        self.client.post(reverse("client_login"), {"order_number": self.order.number})
        self.client.post(reverse("client_login"), {"order_number": second.number})

        portal = self.client.get(reverse("client_portal"))
        self.assertEqual(len(portal.context["orders"]), 2)
        self.assertContains(portal, self.order.number)
        self.assertContains(portal, second.number)

    def test_order_detail_requires_saved_browser_access(self):
        self.assertEqual(
            self.client.get(reverse("client_order", args=[self.order.public_id])).status_code,
            404,
        )

    def test_client_notifications_are_marked_read_after_opening(self):
        OrderEvent.objects.create(
            order=self.order,
            kind=OrderEvent.Kind.STATUS,
            new_status=self.order.status,
            public_message="Диагностика началась.",
        )
        token = issue_link(self.order)
        self.client.get(reverse("client_exchange", args=[self.order.public_id, token]))

        first = self.client.get(reverse("client_order", args=[self.order.public_id]))
        self.assertEqual(first.context["unread_count"], 1)
        self.assertContains(first, "Диагностика началась.")
        self.assertContains(first, "Новое")

        second = self.client.get(reverse("client_order", args=[self.order.public_id]))
        self.assertEqual(second.context["unread_count"], 0)
        self.assertContains(second, "Прочитано")

    def test_unknown_order_number_does_not_open_portal(self):
        response = self.client.post(
            reverse("client_login"),
            {"order_number": "M26-0000000000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Заявка с таким номером не найдена")
        self.assertRedirects(self.client.get(reverse("client_portal")), reverse("client_login"))

    def test_client_logout_revokes_browser_session_only(self):
        token = issue_link(self.order)
        self.client.get(reverse("client_exchange", args=[self.order.public_id, token]))
        response = self.client.post(reverse("client_logout"))
        self.assertRedirects(response, reverse("client_login"))
        self.assertRedirects(self.client.get(reverse("client_portal")), reverse("client_login"))
