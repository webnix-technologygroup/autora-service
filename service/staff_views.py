from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .auth import employee_required, is_manager
from .estimates import (
    add_item as estimate_add_item,
)
from .estimates import (
    approve_current,
    set_manual_estimate,
)
from .estimates import (
    delete_item as estimate_delete_item,
)
from .forms import (
    AssignmentForm,
    CommentForm,
    EstimateItemForm,
    ManualApprovalForm,
    PriceForm,
    ScheduleForm,
    StatusForm,
)
from .links import issue_link
from .models import EstimateItem, NotificationLog, Order, OrderComment, OrderEvent, Service
from .notifications import queue_on_commit
from .orders import transition
from .policies import scope_orders
from .scheduling import assign_worker
from .scheduling import update_schedule as schedule_order


def _base_queryset(user):
    return scope_orders(
        user,
        Order.objects.select_related(
            "customer", "vehicle", "service", "assigned_to", "confirmed_by"
        ).prefetch_related("notifications"),
    )


def _role_name(user):
    if user.is_superuser:
        return "Администратор"
    if is_manager(user):
        return "Менеджер"
    return "Мастер"


def _require_perm(user, permission):
    if not (user.is_superuser or user.has_perm(permission)):
        raise PermissionDenied


@employee_required
def staff_dashboard(request):
    orders = _base_queryset(request.user)
    today = timezone.localdate()
    metrics = {
        "new": orders.filter(status=Order.Status.NEW).count(),
        "today": orders.filter(Q(desired_date=today) | Q(confirmed_start_at__date=today)).count(),
        "pending": orders.filter(status__in=[Order.Status.NEW, Order.Status.PENDING]).count(),
        "diagnostics": orders.filter(status=Order.Status.DIAGNOSTICS).count(),
        "approval": orders.filter(status=Order.Status.AWAITING_APPROVAL).count(),
        "repair": orders.filter(status__in=[Order.Status.PARTS, Order.Status.REPAIR]).count(),
        "ready": orders.filter(status=Order.Status.READY).count(),
        "overdue": orders.filter(desired_date__lt=today).exclude(status__in=Order.TERMINAL_STATUSES).count(),
    }
    failed = NotificationLog.objects.filter(
        order__in=orders, status=NotificationLog.Status.FAILED, failed_permanently_at__isnull=True
    ).count()
    return render(
        request,
        "staff/dashboard.html",
        {
            "metrics": metrics,
            "failed_count": failed,
            "urgent": orders.filter(desired_date__lte=today).exclude(status__in=Order.TERMINAL_STATUSES)[:8],
            "recent": orders[:8],
            "mine": orders.filter(assigned_to=request.user)[:8],
            "role_name": _role_name(request.user),
        },
    )


@employee_required
def order_list(request):
    orders = _base_queryset(request.user)
    q = request.GET.get("q", "").strip()[:200]
    status_raw = request.GET.get("status", "")
    status = status_raw if status_raw in Order.Status.values else ""
    service_raw = request.GET.get("service", "")
    service = int(service_raw) if service_raw.isdigit() and int(service_raw) > 0 else None
    assigned_raw = request.GET.get("assigned", "")
    assigned = int(assigned_raw) if assigned_raw.isdigit() and int(assigned_raw) > 0 else None
    date = parse_date(request.GET.get("date", ""))
    allowed_views = {"", "mine", "new", "today", "approval", "ready", "unassigned", "failed"}
    view_raw = request.GET.get("view", "")
    view = view_raw if view_raw in allowed_views else ""
    allowed_sorts = {
        "created_at",
        "-created_at",
        "updated_at",
        "-updated_at",
        "desired_date",
        "-desired_date",
        "status",
    }
    sort_raw = request.GET.get("sort", "-updated_at")
    sort = sort_raw if sort_raw in allowed_sorts else "-updated_at"
    today = timezone.localdate()
    if any(
        (
            status_raw and not status,
            service_raw and service is None,
            assigned_raw and assigned is None,
            request.GET.get("date") and date is None,
            view_raw not in allowed_views,
            sort_raw not in allowed_sorts,
        )
    ):
        messages.warning(request, "Часть некорректных фильтров проигнорирована.")
    if q:
        orders = orders.filter(
            Q(number__icontains=q)
            | Q(customer__name__icontains=q)
            | Q(customer__phone__icontains=q)
            | Q(vehicle__plate__icontains=q)
            | Q(vehicle__vin__icontains=q)
        )
    if status:
        orders = orders.filter(status=status)
    if service:
        orders = orders.filter(service_id=service)
    if assigned:
        orders = orders.filter(assigned_to_id=assigned)
    if date:
        orders = orders.filter(Q(desired_date=date) | Q(confirmed_start_at__date=date))
    if view == "mine":
        orders = orders.filter(assigned_to=request.user)
    elif view == "new":
        orders = orders.filter(status=Order.Status.NEW)
    elif view == "today":
        orders = orders.filter(Q(desired_date=today) | Q(confirmed_start_at__date=today))
    elif view == "approval":
        orders = orders.filter(status=Order.Status.AWAITING_APPROVAL)
    elif view == "ready":
        orders = orders.filter(status=Order.Status.READY)
    elif view == "unassigned":
        orders = orders.filter(assigned_to__isnull=True)
    elif view == "failed":
        orders = orders.filter(notifications__status=NotificationLog.Status.FAILED).distinct()
    paginator = Paginator(orders.order_by(sort), 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    workers = (
        get_user_model()
        .objects.filter(is_active=True, groups__name__in=["Менеджеры", "Мастера"])
        .distinct()
        .order_by("username")
        if is_manager(request.user)
        else get_user_model().objects.filter(pk=request.user.pk)
    )
    return render(
        request,
        "staff/orders.html",
        {
            "page_obj": page_obj,
            "query_without_page": query.urlencode(),
            "statuses": Order.Status.choices,
            "services": Service.objects.filter(is_active=True),
            "workers": workers,
            "role_name": _role_name(request.user),
        },
    )


@employee_required
def order_detail(request, pk):
    order = get_object_or_404(
        _base_queryset(request.user)
        .select_related("estimate_approval_recorded_by")
        .prefetch_related("photos", "events__actor", "comments__author", "estimate_items"),
        pk=pk,
    )
    new_link = request.session.pop(f"new_link:{order.pk}", None)
    return render(
        request,
        "staff/order_detail.html",
        {
            "order": order,
            "status_form": StatusForm(order=order, user=request.user),
            "assignment_form": AssignmentForm(instance=order),
            "schedule_form": ScheduleForm(instance=order),
            "price_form": PriceForm(instance=order),
            "item_form": EstimateItemForm(),
            "comment_form": CommentForm(),
            "role_name": _role_name(request.user),
            "can_manage_finance": request.user.is_superuser
            or request.user.has_perm("service.manage_finance"),
            "can_schedule": request.user.is_superuser or request.user.has_perm("service.manage_schedule"),
            "can_assign": request.user.is_superuser or request.user.has_perm("service.view_all_orders"),
            "can_manage_links": request.user.is_superuser or request.user.has_perm("service.manage_links"),
            "can_retry": request.user.is_superuser or request.user.has_perm("service.retry_notifications"),
            "manual_approval_form": ManualApprovalForm(initial={"version": order.estimate_version}),
            "new_client_url": new_link,
        },
    )


def _mutable_order(user, pk):
    order = get_object_or_404(scope_orders(user, Order.objects.all()), pk=pk)
    if order.is_terminal:
        raise PermissionDenied("Завершённый заказ нельзя изменять.")
    return order


@require_POST
@employee_required
def change_status(request, pk):
    order = _mutable_order(request.user, pk)
    form = StatusForm(request.POST, order=order, user=request.user)
    if form.is_valid():
        try:
            transition(
                order,
                form.cleaned_data["status"],
                request.user,
                form.cleaned_data["public_message"],
                form.cleaned_data["internal_message"],
                form.cleaned_data["expected_status"],
            )
        except ValidationError:
            messages.error(request, "Статус заказа уже изменился. Обновите страницу и повторите действие.")
        else:
            messages.success(request, "Статус изменён.")
    else:
        messages.error(request, "Переход статуса недоступен или заполнен неверно.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def assign_order(request, pk):
    _require_perm(request.user, "service.view_all_orders")
    order = _mutable_order(request.user, pk)
    form = AssignmentForm(request.POST, instance=order)
    if form.is_valid():
        try:
            assign_worker(order.pk, form.cleaned_data["assigned_to"], request.user)
        except ValidationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Ответственный обновлён.")
    else:
        messages.error(request, "Не удалось изменить ответственного.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def update_schedule(request, pk):
    _require_perm(request.user, "service.manage_schedule")
    order = _mutable_order(request.user, pk)
    form = ScheduleForm(request.POST, instance=order)
    if form.is_valid():
        try:
            schedule_order(
                order.pk,
                form.cleaned_data["confirmed_start_at"],
                form.cleaned_data["confirmed_end_at"],
                request.user,
                form.cleaned_data.get("reason", ""),
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Расписание обновлено.")
    else:
        messages.error(request, "Проверьте дату и время.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def update_price(request, pk):
    _require_perm(request.user, "service.manage_finance")
    order = _mutable_order(request.user, pk)
    form = PriceForm(request.POST, instance=order)
    if form.is_valid():
        set_manual_estimate(
            order.pk,
            form.cleaned_data["estimate"],
            form.cleaned_data["estimate_note"],
            form.cleaned_data["final_price"],
            request.user,
        )
        messages.success(request, "Стоимость обновлена.")
    else:
        messages.error(request, "Проверьте значения стоимости.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def add_estimate_item(request, pk):
    _require_perm(request.user, "service.manage_finance")
    order = _mutable_order(request.user, pk)
    form = EstimateItemForm(request.POST)
    if form.is_valid():
        estimate_add_item(order, form, request.user)
        messages.success(request, "Позиция добавлена.")
    else:
        messages.error(request, "Проверьте позицию сметы.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def delete_estimate_item(request, pk, item_id):
    _require_perm(request.user, "service.manage_finance")
    order = _mutable_order(request.user, pk)
    item = get_object_or_404(EstimateItem, pk=item_id, order=order)
    estimate_delete_item(order, item, request.user)
    messages.success(request, "Позиция удалена.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def add_comment(request, pk):
    order = _mutable_order(request.user, pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        OrderComment.objects.create(order=order, author=request.user, text=form.cleaned_data["text"])
        OrderEvent.objects.create(
            order=order,
            kind=OrderEvent.Kind.NOTE,
            actor=request.user,
            internal_message="Добавлен внутренний комментарий",
        )
        messages.success(request, "Комментарий добавлен.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def reissue_link(request, pk):
    _require_perm(request.user, "service.manage_links")
    order = _mutable_order(request.user, pk)
    token = issue_link(order, request.user)
    url = request.build_absolute_uri(reverse("client_exchange", args=[order.public_id, token]))
    request.session[f"new_link:{order.pk}"] = url
    queue_on_commit(order, "link_reissued")
    messages.success(request, "Новая ссылка создана. Она показывается один раз.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def retry_notification(request, pk, notification_id):
    _require_perm(request.user, "service.retry_notifications")
    order = get_object_or_404(scope_orders(request.user, Order.objects.all()), pk=pk)
    notification = get_object_or_404(
        NotificationLog, pk=notification_id, order=order, status=NotificationLog.Status.FAILED
    )
    notification.status = NotificationLog.Status.PENDING
    notification.next_attempt_at = timezone.now()
    notification.failed_permanently_at = None
    notification.last_error = ""
    notification.save(update_fields=["status", "next_attempt_at", "failed_permanently_at", "last_error"])
    OrderEvent.objects.create(
        order=order,
        kind=OrderEvent.Kind.NOTE,
        actor=request.user,
        internal_message=f"Повтор уведомления #{notification.pk}",
    )
    messages.success(request, "Уведомление поставлено в очередь.")
    return redirect("staff_order_detail", pk=pk)


@require_POST
@employee_required
def record_manual_approval(request, pk):
    _require_perm(request.user, "service.manage_finance")
    order = _mutable_order(request.user, pk)
    form = ManualApprovalForm(request.POST)
    if form.is_valid():
        try:
            approve_current(
                order.pk,
                form.cleaned_data["version"],
                form.cleaned_data["method"],
                request.user,
                form.cleaned_data["note"],
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Согласование сметы зафиксировано.")
    else:
        messages.error(request, "Укажите метод и примечание согласования.")
    return redirect("staff_order_detail", pk=pk)
