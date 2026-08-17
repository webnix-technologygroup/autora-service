from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Order


def _validate_interval(start, end):
    if (start is None) != (end is None):
        raise ValidationError("Начало и окончание расписания должны быть указаны вместе.")
    if start is None and end is None:
        return
    if timezone.is_naive(start) or timezone.is_naive(end):
        raise ValidationError("Время расписания должно содержать часовой пояс.")
    if end <= start:
        raise ValidationError("Окончание должно быть позже начала.")
    if start < timezone.now():
        raise ValidationError("Подтверждённое время не может быть в прошлом.")


def _has_conflict(order_id, worker_id, start, end):
    if not worker_id or not start or not end:
        return False
    return (
        Order.objects.exclude(pk=order_id)
        .exclude(status__in=Order.TERMINAL_STATUSES)
        .filter(
            assigned_to_id=worker_id,
            confirmed_start_at__lt=end,
            confirmed_end_at__gt=start,
        )
        .exists()
    )


def update_schedule(order_id, start, end, actor, reason=""):
    _validate_interval(start, end)
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.is_terminal:
            raise ValidationError("Завершённый заказ нельзя перепланировать.")
        if order.assigned_to_id:
            get_user_model().objects.select_for_update().get(pk=order.assigned_to_id)
        if _has_conflict(order.pk, order.assigned_to_id, start, end):
            raise ValidationError("У ответственного уже есть заказ в этом интервале.")
        previous = order.confirmed_start_at
        clearing = start is None and end is None
        order.confirmed_start_at = start
        order.confirmed_end_at = end
        order.confirmed_by = None if clearing else actor
        order.booking_confirmed_at = None if clearing else timezone.now()
        order.full_clean(exclude=["estimate", "final_price"])
        order.save(
            update_fields=[
                "confirmed_start_at",
                "confirmed_end_at",
                "confirmed_by",
                "booking_confirmed_at",
                "updated_at",
            ]
        )
        from .models import OrderEvent
        from .notifications import queue_on_commit

        OrderEvent.objects.create(
            order=order,
            kind=OrderEvent.Kind.SCHEDULE,
            actor=actor,
            public_message=(
                "Подтверждённое время визита снято."
                if clearing
                else "Время визита подтверждено или обновлено."
            ),
            internal_message=f"{previous or '—'} → {start or 'очищено'}; {reason}"[:1000],
        )
        if not clearing:
            queue_on_commit(order, "schedule_changed")
        return order


def assign_worker(order_id, worker, actor):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.is_terminal:
            raise ValidationError("Завершённый заказ нельзя изменить.")
        if worker:
            get_user_model().objects.select_for_update().get(pk=worker.pk)
        if _has_conflict(
            order.pk,
            worker.pk if worker else None,
            order.confirmed_start_at,
            order.confirmed_end_at,
        ):
            raise ValidationError("У выбранного сотрудника уже есть заказ в этом интервале.")
        previous = order.assigned_to
        order.assigned_to = worker
        order.save(update_fields=["assigned_to", "updated_at"])
        from .models import OrderEvent

        OrderEvent.objects.create(
            order=order,
            kind=OrderEvent.Kind.ASSIGNMENT,
            actor=actor,
            internal_message=f"Ответственный: {previous or '—'} → {worker or '—'}"[:1000],
        )
        return order
