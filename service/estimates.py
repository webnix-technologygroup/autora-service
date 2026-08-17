from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from .models import EstimateItem, Order, OrderEvent
from .notifications import queue_on_commit


def _total(order):
    return order.estimate_items.aggregate(
        total=models.Sum(
            models.F("quantity") * models.F("unit_price"),
            output_field=models.DecimalField(max_digits=12, decimal_places=2),
        )
    )["total"] or Decimal("0.00")


def _invalidate_approval(order):
    order.estimate_approved = False
    order.approved_estimate_amount = None
    order.estimate_approval_method = ""
    order.estimate_approval_recorded_at = None
    order.estimate_approval_recorded_by = None
    order.estimate_approval_note = ""


def recalculate_locked(order, actor, summary):
    old = order.estimate or Decimal("0.00")
    total = _total(order)
    order.estimate = total
    order.estimate_version += 1
    _invalidate_approval(order)
    order.save(
        update_fields=[
            "estimate",
            "estimate_version",
            "estimate_approved",
            "approved_estimate_amount",
            "estimate_approval_method",
            "estimate_approval_recorded_at",
            "estimate_approval_recorded_by",
            "estimate_approval_note",
            "updated_at",
        ]
    )
    OrderEvent.objects.create(
        order=order,
        kind=OrderEvent.Kind.PRICE,
        actor=actor,
        internal_message=f"{summary}: {old} → {total}; версия {order.estimate_version}"[:1000],
    )
    return total


def add_item(order, form, actor):
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.is_terminal:
            raise PermissionDenied("Завершённый заказ нельзя изменять.")
        item = form.save(commit=False)
        item.order = locked
        item.full_clean()
        item.save()
        recalculate_locked(locked, actor, f"Добавлена позиция {item.name}")
        return item


def delete_item(order, item, actor):
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.is_terminal:
            raise PermissionDenied("Завершённый заказ нельзя изменять.")
        name = item.name
        EstimateItem.objects.get(pk=item.pk, order=locked).delete()
        return recalculate_locked(locked, actor, f"Удалена позиция {name}")


def set_manual_estimate(order_id, amount, note, final_price, actor):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.is_terminal:
            raise PermissionDenied("Завершённый заказ нельзя изменять.")
        if order.estimate_items.exists():
            amount = _total(order)
        meaningful_change = order.estimate != amount
        order.estimate = amount
        order.estimate_note = note
        order.final_price = final_price
        if meaningful_change:
            order.estimate_version += 1
            _invalidate_approval(order)
        order.full_clean(exclude=["vehicle"])
        order.save()
        OrderEvent.objects.create(
            order=order,
            kind=OrderEvent.Kind.PRICE,
            actor=actor,
            internal_message=f"Стоимость обновлена; версия {order.estimate_version}",
        )
        return order


def approve_current(order_id, version, method, actor=None, note=""):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.is_terminal:
            raise PermissionDenied("Завершённый заказ нельзя изменять.")
        if order.status != Order.Status.AWAITING_APPROVAL:
            raise ValidationError("Согласование доступно только на этапе ожидания согласования.")
        if order.estimate is None:
            raise ValidationError("Смета ещё не подготовлена.")
        if order.estimate < 0:
            raise ValidationError("Сумма сметы не может быть отрицательной.")
        if int(version) != order.estimate_version:
            raise ValidationError("Смета изменилась. Обновите страницу.")
        if (
            order.estimate_approved
            and order.approved_estimate_amount == order.estimate
            and order.estimate_approval_recorded_at
        ):
            return order, False
        order.estimate_approved = True
        order.approved_estimate_amount = order.estimate
        order.estimate_approval_method = method
        order.estimate_approval_recorded_at = timezone.now()
        order.estimate_approval_recorded_by = actor
        order.estimate_approval_note = note
        order.save(
            update_fields=[
                "estimate_approved",
                "approved_estimate_amount",
                "estimate_approval_method",
                "estimate_approval_recorded_at",
                "estimate_approval_recorded_by",
                "estimate_approval_note",
                "updated_at",
            ]
        )
        OrderEvent.objects.create(
            order=order,
            kind=OrderEvent.Kind.PRICE,
            actor=actor,
            public_message="Предварительная смета согласована.",
            internal_message=f"Согласована версия {version}; метод {method}"[:1000],
        )
        queue_on_commit(order, "estimate_approved")
        return order, True
