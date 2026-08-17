from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from service.models import Customer, Order, Service, Vehicle


@override_settings(CLIENT_TOKEN_ENCRYPTION_KEYS=["test-encryption-key"], EMAIL_ENABLED=False)
class MotorCase(TestCase):
    def setUp(self):
        cache.clear()
        self.service = Service.objects.create(
            name="Диагностика", slug="diagnostics", description="Проверка", price_from=Decimal("900")
        )
        self.customer = Customer.objects.create(
            name="Клиент", phone="+380501234567", email="client@example.invalid"
        )
        self.vehicle = Vehicle.objects.create(customer=self.customer, make="Toyota", model="Camry", year=2020)
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

    def employee(self, name="worker", group="Мастера", permissions=()):
        user = User.objects.create_user(name, password="test-password", is_staff=True)
        user.groups.add(Group.objects.get_or_create(name=group)[0])
        for codename in permissions:
            user.user_permissions.add(Permission.objects.get(codename=codename))
        return user

    def tearDown(self):
        cache.clear()
        super().tearDown()
