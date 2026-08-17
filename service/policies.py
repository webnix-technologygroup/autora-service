from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet

from .models import Order

MANAGER_TRANSITIONS = {
    "new": {"pending", "booked", "canceled"},
    "pending": {"booked", "canceled", "no_show"},
    "booked": {"accepted", "canceled", "no_show"},
    "accepted": {"diagnostics", "canceled"},
    "diagnostics": {"awaiting_approval", "parts", "repair"},
    "awaiting_approval": {"parts", "repair", "canceled"},
    "parts": {"repair", "canceled"},
    "repair": {"ready", "canceled"},
    "ready": {"done"},
}
MECHANIC_TRANSITIONS = {
    "accepted": {"diagnostics"},
    "diagnostics": {"awaiting_approval"},
    "awaiting_approval": {"parts", "repair"},
    "parts": {"repair"},
    "repair": {"ready"},
}


def scope_orders(user, queryset: QuerySet | None = None):
    queryset = queryset if queryset is not None else Order.objects.all()
    if user.is_superuser or user.has_perm("service.view_all_orders"):
        return queryset
    visible = Q(assigned_to=user)
    if user.has_perm("service.view_unassigned_orders"):
        visible |= Q(assigned_to__isnull=True)
    return queryset.filter(visible)


def can_access_order(user, order: Order) -> bool:
    return bool(user.is_authenticated and scope_orders(user, Order.objects.filter(pk=order.pk)).exists())


def require_order_access(user, order: Order) -> None:
    if not can_access_order(user, order):
        raise PermissionDenied


def has_current_estimate_approval(order: Order) -> bool:
    return bool(
        order.estimate_approved
        and order.estimate is not None
        and order.approved_estimate_amount == order.estimate
        and order.estimate_approval_recorded_at
    )


def allowed_transitions(user, order: Order):
    if order.is_terminal:
        return set()
    if user.is_superuser:
        choices = set(MANAGER_TRANSITIONS.get(order.status, set()))
    elif user.has_perm("service.view_all_orders"):
        choices = set(MANAGER_TRANSITIONS.get(order.status, set()))
    elif order.assigned_to_id == user.id:
        choices = set(MECHANIC_TRANSITIONS.get(order.status, set()))
    else:
        return set()
    if (
        order.status == Order.Status.AWAITING_APPROVAL
        and order.estimate
        and not has_current_estimate_approval(order)
    ):
        choices -= {Order.Status.PARTS, Order.Status.REPAIR}
    return choices
