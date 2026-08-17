from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..links import issue_link
from ..models import Customer, EstimateItem, Order, Service, Vehicle
from ..policies import allowed_transitions, scope_orders


@override_settings(
    CLIENT_TOKEN_ENCRYPTION_KEYS=["test-encryption-key"],
    EMAIL_ENABLED=False,
)
class BaseCase(TestCase):
    def setUp(self):
        self.service = Service.objects.create(
            name="Диагностика",
            slug="diagnostics",
            description="Проверка",
            price_from=Decimal("900.00"),
        )
        self.customer = Customer.objects.create(
            name="Клиент",
            phone="+380501234567",
            email="client@example.invalid",
        )
        self.vehicle = Vehicle.objects.create(
            customer=self.customer,
            make="Toyota",
            model="Camry",
            year=2020,
        )
        self.order = Order.objects.create(
            number=Order.new_number(),
            customer=self.customer,
            vehicle=self.vehicle,
            service=self.service,
            service_name=self.service.name,
            service_price_from=self.service.price_from,
            problem="Шум",
            desired_date=timezone.localdate() + timedelta(days=2),
        )


class PublicPageTests(BaseCase):
    def test_public_pages(self):
        for name in ("home", "services", "about", "contacts", "privacy", "consent"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_inactive_service_returns_404(self):
        self.service.is_active = False
        self.service.save(update_fields=["is_active"])
        response = self.client.get(reverse("service_detail", args=[self.service.slug]))
        self.assertEqual(response.status_code, 404)


class ClientAccessTests(BaseCase):
    def test_token_is_exchanged_for_clean_session_url(self):
        token = issue_link(self.order)
        exchange = reverse("client_exchange", args=[self.order.public_id, token])
        response = self.client.get(exchange)
        self.assertRedirects(response, reverse("client_portal"))
        portal = self.client.get(reverse("client_portal"))
        self.assertEqual(portal.status_code, 200)
        self.assertNotContains(portal, token)

    def test_revocation_immediately_invalidates_session(self):
        token = issue_link(self.order)
        self.client.get(reverse("client_exchange", args=[self.order.public_id, token]))
        self.order.access_links.update(revoked_at=timezone.now())
        self.assertEqual(self.client.get(reverse("client_portal")).status_code, 404)

    def test_reissue_invalidates_old_exchange_url(self):
        old_token = issue_link(self.order)
        new_token = issue_link(self.order)
        old_url = reverse("client_exchange", args=[self.order.public_id, old_token])
        new_url = reverse("client_exchange", args=[self.order.public_id, new_token])
        self.assertEqual(self.client.get(old_url).status_code, 404)
        self.assertEqual(self.client.get(new_url).status_code, 302)


class RolePolicyTests(BaseCase):
    def setUp(self):
        super().setUp()
        managers = Group.objects.create(name="Менеджеры")
        mechanics = Group.objects.create(name="Мастера")
        self.manager = User.objects.create_user("manager", password="test-password")
        self.mechanic = User.objects.create_user("mechanic", password="test-password")
        self.other_mechanic = User.objects.create_user("other", password="test-password")
        self.manager.groups.add(managers)
        self.mechanic.groups.add(mechanics)
        self.other_mechanic.groups.add(mechanics)
        permission = Permission.objects.get(codename="view_all_orders")
        self.manager.user_permissions.add(permission)
        self.order.assigned_to = self.mechanic
        self.order.status = Order.Status.ACCEPTED
        self.order.save(update_fields=["assigned_to", "status"])

    def test_mechanic_sees_only_assigned_order(self):
        self.assertTrue(scope_orders(self.mechanic).filter(pk=self.order.pk).exists())
        self.assertFalse(scope_orders(self.other_mechanic).filter(pk=self.order.pk).exists())

    def test_role_specific_transitions(self):
        self.assertIn(Order.Status.DIAGNOSTICS, allowed_transitions(self.mechanic, self.order))
        self.assertNotIn(Order.Status.CANCELED, allowed_transitions(self.mechanic, self.order))

    def test_terminal_order_has_no_normal_transitions(self):
        self.order.status = Order.Status.DONE
        self.order.save(update_fields=["status"])
        self.assertEqual(allowed_transitions(self.manager, self.order), set())


class EstimateModelTests(BaseCase):
    def test_decimal_total(self):
        item = EstimateItem.objects.create(
            order=self.order,
            item_type=EstimateItem.ItemType.WORK,
            name="Работа",
            quantity=Decimal("1.50"),
            unit_price=Decimal("100.20"),
        )
        self.assertEqual(item.total, Decimal("150.3000"))


class DataIntegrityTests(BaseCase):
    def test_vehicle_must_belong_to_order_customer(self):
        another = Customer.objects.create(name="Другой", phone="+380501234568")
        wrong_vehicle = Vehicle.objects.create(customer=another, make="Ford", model="Focus")
        self.order.vehicle = wrong_vehicle
        with self.assertRaises(ValidationError):
            self.order.full_clean()
