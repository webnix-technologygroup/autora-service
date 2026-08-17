from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from service.models import Customer, EstimateItem, Order, OrderEvent, Service, SiteSettings, Vehicle


class Command(BaseCommand):
    help = "Идемпотентно заполняет сайт демонстрационными данными без создания пользователей"

    def handle(self, *args, **options):
        SiteSettings.objects.update_or_create(
            singleton=1,
            defaults={
                "name": "AUTORA",
                "phone": "+380 44 334 72 18",
                "email": "hello@autora.service",
                "address": "Киев, ул. Промышленная, 12",
                "working_hours": "Пн–Сб, 08:00–20:00",
                "about": "Технологичный автосервис с прозрачным процессом и вниманием к деталям.",
            },
        )
        items = [
            ("diagnostics", "Компьютерная диагностика", "Диагностика", 900, 45, "Сканирование электронных блоков, проверка параметров и понятный отчёт по неисправностям."),
            ("maintenance", "Регламентное ТО", "ТО", 1800, 90, "Масло, фильтры и контроль ключевых узлов по регламенту производителя."),
            ("brakes", "Тормозная система", "Тормоза", 1400, 120, "Проверка дисков, колодок, суппортов и тормозной жидкости."),
            ("suspension", "Подвеска и рулевое", "Ходовая", 1600, 120, "Поиск люфтов, шумов и причин нестабильного поведения автомобиля."),
            ("engine", "Двигатель", "Двигатель", 2200, 180, "Диагностика механики и навесного оборудования без замены деталей наугад."),
            ("climate", "Климатическая система", "Климат", 1200, 75, "Проверка герметичности, давления и производительности системы."),
            ("electric", "Автоэлектрика", "Электрика", 1500, 90, "Поиск утечек тока, неисправностей проводки, датчиков и исполнительных узлов."),
            ("prepurchase", "Проверка перед покупкой", "Покупка", 2800, 150, "Комплексная проверка кузова, агрегатов и электронных систем перед сделкой."),
        ]
        services = {}
        for index, (slug, name, icon, price, duration, description) in enumerate(items):
            service, _ = Service.objects.update_or_create(slug=slug, defaults={"name": name, "icon": icon, "price_from": price, "duration_minutes": duration, "description": description, "order": index, "is_active": True})
            services[slug] = service
        demos = [
            ("Анна Левченко", "+380501110101", "Volkswagen", "Tiguan", 2021, "KA4102IX", "diagnostics", "Вибрация на холодном запуске.", Order.Status.DIAGNOSTICS, 3200),
            ("Максим Бондарь", "+380501110102", "BMW", "320i", 2019, "KA8821CT", "brakes", "Биение при торможении.", Order.Status.AWAITING_APPROVAL, 8600),
            ("Ирина Коваль", "+380501110103", "Skoda", "Octavia", 2020, "AA7284KP", "maintenance", "Плановое ТО на пробеге 75 000 км.", Order.Status.BOOKED, 4900),
            ("Дмитрий Савченко", "+380501110104", "Volvo", "XC60", 2018, "KA3307MM", "suspension", "Стук справа на мелких неровностях.", Order.Status.REPAIR, 12400),
        ]
        for index, data in enumerate(demos, start=1):
            name, phone, make, model, year, plate, slug, problem, status, estimate = data
            customer, _ = Customer.objects.update_or_create(phone=phone, defaults={"name": name, "email": f"demo{index}@example.test", "is_demo": True})
            vehicle, _ = Vehicle.objects.update_or_create(customer=customer, plate=plate, defaults={"make": make, "model": model, "year": year})
            service = services[slug]
            order, _ = Order.objects.update_or_create(number=f"DEMO-26-{index:03d}", defaults={"customer": customer, "vehicle": vehicle, "service": service, "service_name": service.name, "service_price_from": service.price_from, "problem": problem, "desired_date": timezone.localdate() + timedelta(days=index), "status": status, "estimate": Decimal(estimate), "is_demo": True})
            OrderEvent.objects.get_or_create(order=order, kind="created", defaults={"new_status": Order.Status.NEW, "public_message": "Заявка принята сервисом."})
            EstimateItem.objects.get_or_create(order=order, name="Диагностика и работы", defaults={"item_type": "work", "quantity": 1, "unit_price": Decimal(estimate), "order_index": 1})
        self.stdout.write(self.style.SUCCESS("Демо-данные сайта готовы. Пользователи не создавались."))
