from django.contrib import admin, messages
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    ClientAccess,
    Customer,
    EstimateItem,
    NotificationLog,
    Order,
    OrderComment,
    OrderEvent,
    OrderPhoto,
    Service,
    SiteSettings,
    Vehicle,
)

admin.site.site_header = "AUTORA · Control Center"
admin.site.site_title = "AUTORA"
admin.site.index_title = "Состояние мастерской"
admin.site.index_template = "admin/index.html"
_original_each_context = admin.site.each_context


def motor_each_context(request):
    context = _original_each_context(request)
    context["motor_metrics"] = {
        "new": Order.objects.filter(status=Order.Status.NEW).count(),
        "active": Order.objects.exclude(status__in=Order.TERMINAL_STATUSES).count(),
        "failed": NotificationLog.objects.filter(status=NotificationLog.Status.FAILED).count(),
        "expired_links": ClientAccess.objects.filter(
            expires_at__lte=timezone.now(), revoked_at__isnull=True
        ).count(),
        "services": Service.objects.filter(is_active=True).count(),
    }
    return context


admin.site.each_context = motor_each_context
# Django's native permission contract is intentionally preserved: a user must
# be active and staff. Superusers created with `createsuperuser` satisfy both flags.
# The previous superuser-only lambda made diagnosis of login/CSRF failures
# needlessly opaque and could lock out valid staff administrators.
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_staff


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class PhotoInline(ReadOnlyInline):
    model = OrderPhoto
    fields = ("original_name", "content_type", "size", "uploaded_at")
    readonly_fields = fields


class EventInline(ReadOnlyInline):
    model = OrderEvent
    fields = ("kind", "old_status", "new_status", "public_message", "internal_message", "actor", "created_at")
    readonly_fields = fields
    ordering = ("-created_at",)


class EstimateInline(ReadOnlyInline):
    model = EstimateItem
    fields = ("item_type", "name", "quantity", "unit_price", "item_total")
    readonly_fields = fields

    @admin.display(description="Сумма")
    def item_total(self, obj):
        return f"{obj.total} ₴"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "customer",
        "vehicle",
        "status_badge",
        "service_name",
        "confirmed_start_at",
        "assigned_to",
        "amount",
        "staff_link",
    )
    list_filter = ("status", "service", "desired_date", "assigned_to", "is_demo")
    search_fields = ("number", "customer__name", "customer__phone", "vehicle__plate", "vehicle__vin")
    date_hierarchy = "created_at"
    list_select_related = ("customer", "vehicle", "service", "assigned_to")
    autocomplete_fields = ("customer", "vehicle", "service", "assigned_to")
    inlines = (PhotoInline, EstimateInline, EventInline)
    readonly_fields = (
        "public_id",
        "number",
        "status",
        "service_name",
        "service_price_from",
        "customer",
        "vehicle",
        "service",
        "problem",
        "desired_date",
        "desired_time",
        "confirmed_start_at",
        "confirmed_end_at",
        "confirmed_by",
        "booking_confirmed_at",
        "assigned_to",
        "estimate",
        "estimate_note",
        "estimate_approval_recorded_at",
        "estimate_approval_recorded_by",
        "estimate_approval_note",
        "final_price",
        "is_demo",
        "created_at",
        "updated_at",
        "staff_link",
    )
    fieldsets = (
        (
            "Заказ",
            {
                "fields": (
                    "number",
                    "status",
                    "staff_link",
                    "customer",
                    "vehicle",
                    "service",
                    "service_name",
                    "service_price_from",
                )
            },
        ),
        ("Заявка", {"fields": ("problem", "desired_date", "desired_time")}),
        (
            "Подтверждённое расписание",
            {"fields": ("confirmed_start_at", "confirmed_end_at", "confirmed_by", "booking_confirmed_at")},
        ),
        (
            "Ответственный и стоимость",
            {
                "fields": (
                    "assigned_to",
                    "estimate",
                    "estimate_note",
                    "estimate_approval_recorded_at",
                    "estimate_approval_recorded_by",
                    "estimate_approval_note",
                    "final_price",
                )
            },
        ),
        (
            "Системные поля",
            {"classes": ("collapse",), "fields": ("public_id", "is_demo", "created_at", "updated_at")},
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Статус")
    def status_badge(self, obj):
        return format_html(
            '<span class="motor-badge status-{}">{}</span>', obj.status, obj.get_status_display()
        )

    @admin.display(description="Стоимость")
    def amount(self, obj):
        return f"{obj.final_price or obj.estimate or '—'} ₴" if obj.final_price or obj.estimate else "—"

    @admin.display(description="Операционный кабинет")
    def staff_link(self, obj):
        return (
            format_html(
                '<a class="button" href="{}">Открыть заказ</a>', reverse("staff_order_detail", args=[obj.pk])
            )
            if obj.pk
            else "—"
        )


@admin.register(OrderEvent)
class EventAdmin(admin.ModelAdmin):
    list_display = ("order_link", "kind", "old_status", "new_status", "actor", "created_at")
    list_filter = ("kind", "new_status", "created_at")
    search_fields = ("order__number", "public_message", "internal_message")
    date_hierarchy = "created_at"
    readonly_fields = (
        "order",
        "kind",
        "old_status",
        "new_status",
        "public_message",
        "internal_message",
        "actor",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Заказ", ordering="order__number")
    def order_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:service_order_change", args=[obj.order_id]),
            obj.order.number,
        )


@admin.action(description="Повторить выбранные ошибочные уведомления")
def retry_failed(modeladmin, request, queryset):
    count = queryset.filter(status=NotificationLog.Status.FAILED).update(
        status=NotificationLog.Status.PENDING,
        next_attempt_at=timezone.now(),
        failed_permanently_at=None,
        last_error="",
    )
    messages.success(request, f"Поставлено в очередь: {count}")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order_link",
        "channel",
        "event_type",
        "recipient_hint",
        "status",
        "attempts",
        "next_attempt_at",
        "sent_at",
    )
    list_filter = ("status", "channel", "event_type")
    search_fields = ("order__number", "recipient_hint", "dedupe_key")
    date_hierarchy = "created_at"
    actions = (retry_failed,)
    readonly_fields = (
        "order",
        "channel",
        "event_type",
        "recipient_hint",
        "status",
        "attempts",
        "last_error",
        "dedupe_key",
        "next_attempt_at",
        "locked_at",
        "failed_permanently_at",
        "created_at",
        "sent_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Заказ")
    def order_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>', reverse("staff_order_detail", args=[obj.order_id]), obj.order.number
        )


@admin.action(description="Отозвать выбранные активные ссылки")
def revoke_links(modeladmin, request, queryset):
    count = queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
    messages.success(request, f"Отозвано ссылок: {count}")


@admin.register(ClientAccess)
class ClientAccessAdmin(admin.ModelAdmin):
    list_display = (
        "order_link",
        "state",
        "masked_hash",
        "created_by",
        "created_at",
        "expires_at",
        "revoked_at",
    )
    list_filter = ("revoked_at", "expires_at")
    search_fields = ("order__number",)
    actions = (revoke_links,)
    readonly_fields = (
        "order",
        "masked_hash",
        "token_hash",
        "token_ciphertext",
        "session_version",
        "encryption_key_version",
        "expires_at",
        "revoked_at",
        "created_at",
        "created_by",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Заказ")
    def order_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>', reverse("staff_order_detail", args=[obj.order_id]), obj.order.number
        )

    @admin.display(description="Hash")
    def masked_hash(self, obj):
        return obj.token_hash[:8] + "…" + obj.token_hash[-6:]

    @admin.display(description="Состояние")
    def state(self, obj):
        return "Активна" if obj.is_valid() else ("Отозвана" if obj.revoked_at else "Истекла")


@admin.register(EstimateItem)
class EstimateItemAdmin(admin.ModelAdmin):
    list_display = ("order", "item_type", "name", "quantity", "unit_price", "item_total")
    list_filter = ("item_type",)
    search_fields = ("order__number", "name")
    readonly_fields = ("order", "item_type", "name", "quantity", "unit_price", "order_index")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Сумма")
    def item_total(self, obj):
        return f"{obj.total} ₴"


@admin.register(OrderComment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("order", "author", "created_at", "short_text")
    search_fields = ("order__number", "text", "author__username")
    readonly_fields = ("order", "author", "text", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Текст")
    def short_text(self, obj):
        return obj.text[:80]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "masked_phone", "email", "order_count", "vehicle_count", "is_demo", "created_at")
    search_fields = ("name", "phone", "email")
    list_filter = ("is_demo", "created_at")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_orders=Count("orders", distinct=True), _vehicles=Count("vehicles", distinct=True))
        )

    @admin.display(description="Телефон", ordering="phone")
    def masked_phone(self, obj):
        return "*" * max(0, len(obj.phone) - 4) + obj.phone[-4:]

    @admin.display(description="Заказы", ordering="_orders")
    def order_count(self, obj):
        return obj._orders

    @admin.display(description="Авто", ordering="_vehicles")
    def vehicle_count(self, obj):
        return obj._vehicles


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("make", "model", "year", "plate", "masked_vin", "customer_link", "order_count")
    search_fields = ("make", "model", "plate", "vin", "customer__phone")
    list_filter = ("make", "year")
    autocomplete_fields = ("customer",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("customer").annotate(_orders=Count("orders"))

    @admin.display(description="VIN")
    def masked_vin(self, obj):
        return obj.vin[:3] + "***" + obj.vin[-4:] if obj.vin else "—"

    @admin.display(description="Клиент")
    def customer_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:service_customer_change", args=[obj.customer_id]),
            obj.customer,
        )

    @admin.display(description="Заказы", ordering="_orders")
    def order_count(self, obj):
        return obj._orders


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "price_from", "duration_minutes", "is_active", "order", "preview")
    list_editable = ("is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        ("Услуга", {"fields": ("name", "slug", "description", "icon")}),
        ("Параметры", {"fields": ("price_from", "duration_minutes", "is_active", "order")}),
    )

    @admin.display(description="Публичная страница")
    def preview(self, obj):
        return format_html(
            '<a href="{}" target="_blank">Открыть ↗</a>', reverse("service_detail", args=[obj.slug])
        )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Бренд", {"fields": ("name", "about")}),
        ("Контакты", {"fields": ("phone", "email", "address", "working_hours")}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
