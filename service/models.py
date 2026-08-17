import secrets
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class SiteSettings(models.Model):
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    name = models.CharField("Название", max_length=100, default="AUTORA")
    phone = models.CharField("Телефон", max_length=40, default="+380 44 555 01 20")
    email = models.EmailField(default="service@example.test")
    address = models.CharField("Адрес", max_length=200, default="Киев")
    working_hours = models.CharField(max_length=100, default="Пн–Сб, 08:00–20:00")
    about = models.TextField(default="Независимый автосервис с прозрачным процессом обработки заявок.")

    class Meta:
        verbose_name = verbose_name_plural = "Настройки сайта"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.singleton = 1
        super().save(*args, **kwargs)


class Service(models.Model):
    name = models.CharField("Название", max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(max_length=1500)
    price_from = models.DecimalField(
        "Цена от", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    icon = models.CharField(max_length=8, default="⚙")
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    email = models.EmailField(blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} · {self.phone[-4:].rjust(len(self.phone), '*')}"


class Vehicle(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="vehicles")
    make = models.CharField(max_length=60)
    model = models.CharField(max_length=60)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    plate = models.CharField(max_length=20, blank=True, db_index=True)
    vin = models.CharField(max_length=17, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "plate"], condition=~Q(plate=""), name="unique_customer_plate"
            ),
            models.UniqueConstraint(
                fields=["customer", "vin"], condition=~Q(vin=""), name="unique_customer_vin"
            ),
        ]

    def __str__(self):
        return f"{self.make} {self.model}"


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая заявка"
        PENDING = "pending", "Ожидает подтверждения"
        BOOKED = "booked", "Запись подтверждена"
        ACCEPTED = "accepted", "Автомобиль принят"
        DIAGNOSTICS = "diagnostics", "Диагностика"
        AWAITING_APPROVAL = "awaiting_approval", "Ожидает согласования"
        PARTS = "parts", "Ожидаются запчасти"
        REPAIR = "repair", "Ремонт"
        READY = "ready", "Готов к выдаче"
        DONE = "done", "Завершён"
        CANCELED = "canceled", "Отменён"
        NO_SHOW = "no_show", "Клиент не приехал"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="orders")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="orders")
    service_name = models.CharField(max_length=120)
    service_price_from = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    problem = models.TextField(max_length=3000)
    desired_date = models.DateField()
    desired_time = models.TimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)  # legacy confirmation timestamp
    confirmed_start_at = models.DateTimeField(null=True, blank=True)
    confirmed_end_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="confirmed_orders"
    )
    booking_confirmed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_orders",
        limit_choices_to={"is_active": True, "is_staff": True},
    )
    estimate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))]
    )
    estimate_note = models.CharField(max_length=500, blank=True)
    estimate_approved = models.BooleanField(default=False)  # legacy compatibility
    estimate_approval_recorded_at = models.DateTimeField(null=True, blank=True)
    estimate_approval_recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="estimate_approvals"
    )
    estimate_approval_note = models.CharField(max_length=500, blank=True)
    estimate_version = models.PositiveIntegerField(default=1)
    approved_estimate_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estimate_approval_method = models.CharField(max_length=40, blank=True)
    final_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))]
    )
    internal_notes = models.TextField(max_length=3000, blank=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "desired_date"]),
            models.Index(fields=["assigned_to", "status"]),
        ]
        permissions = [
            ("view_all_orders", "Может видеть все заказы"),
            ("view_unassigned_orders", "Может видеть неназначенные заказы"),
            ("manage_schedule", "Может подтверждать расписание"),
            ("manage_finance", "Может управлять сметой"),
            ("manage_links", "Может перевыпускать клиентские ссылки"),
            ("retry_notifications", "Может повторять уведомления"),
        ]

    TERMINAL_STATUSES = {Status.DONE, Status.CANCELED, Status.NO_SHOW}

    def __str__(self):
        return f"{self.number} · {self.vehicle}"

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL_STATUSES

    @staticmethod
    def new_number():
        return f"M{timezone.now():%y}-{secrets.token_hex(3).upper()}"

    def clean(self):
        super().clean()
        if self.vehicle_id and self.customer_id and self.vehicle.customer_id != self.customer_id:
            raise ValidationError({"vehicle": "Автомобиль принадлежит другому клиенту."})
        if (
            self.confirmed_end_at
            and self.confirmed_start_at
            and self.confirmed_end_at <= self.confirmed_start_at
        ):
            raise ValidationError({"confirmed_end_at": "Окончание должно быть позже начала."})


class ClientAccess(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="access_links")
    token_hash = models.CharField(max_length=64, unique=True)
    token_ciphertext = models.TextField(blank=True)
    encryption_key_version = models.PositiveSmallIntegerField(default=1)
    session_version = models.UUIDField(default=uuid.uuid4)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Доступ к заказу {self.order.number} · #{self.pk}"

    def is_valid(self):
        return not self.revoked_at and self.expires_at > timezone.now()


class OrderPhoto(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="orders/private/")
    original_name = models.CharField(max_length=120)
    content_type = models.CharField(max_length=20)
    size = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name or f"Фото #{self.pk}"


class OrderEvent(models.Model):
    class Kind(models.TextChoices):
        CREATED = "created", "Создание"
        STATUS = "status", "Статус"
        ASSIGNMENT = "assignment", "Назначение"
        PRICE = "price", "Стоимость"
        SCHEDULE = "schedule", "Дата"
        LINK = "link", "Клиентская ссылка"
        NOTE = "note", "Комментарий"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    old_status = models.CharField(max_length=24, blank=True)
    new_status = models.CharField(max_length=24, blank=True)
    public_message = models.CharField(max_length=500, blank=True)
    internal_message = models.CharField(max_length=1000, blank=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order.number} · {self.get_kind_display()}"


class OrderComment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Комментарий к {self.order.number} · #{self.pk}"


class EstimateItem(models.Model):
    class ItemType(models.TextChoices):
        WORK = "work", "Работа"
        PART = "part", "Деталь"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="estimate_items")
    name = models.CharField(max_length=160)
    item_type = models.CharField(max_length=8, choices=ItemType.choices)
    quantity = models.DecimalField(
        max_digits=8, decimal_places=2, default=1, validators=[MinValueValidator(Decimal("0.01"))]
    )
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    order_index = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order_index", "id"]

    def __str__(self):
        return self.name

    @property
    def total(self):
        return self.quantity * self.unit_price


class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        TELEGRAM = "telegram", "Telegram"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        PROCESSING = "processing", "Обрабатывается"
        SENT = "sent", "Отправлено"
        FAILED = "failed", "Ошибка"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=12, choices=Channel.choices)
    event_type = models.CharField(max_length=40)
    recipient_hint = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    failed_permanently_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    event_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    dedupe_key = models.CharField(max_length=160, unique=True)
    worker_id = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["status", "locked_at"]),
        ]

    def __str__(self):
        return f"{self.order.number} · {self.get_channel_display()} · {self.event_type}"


class Submission(models.Model):
    key_hash = models.CharField(max_length=64, unique=True)
    session_key = models.CharField(max_length=40, db_index=True)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True, default=timezone.now)

    def __str__(self):
        return f"Submission #{self.pk}"
