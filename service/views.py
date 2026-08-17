import hashlib
import logging
import secrets

from django.contrib import messages
from django.contrib.auth import logout
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .auth import is_employee
from .client_access import cabinet_links, clear_cabinet, current_link, establish, forget_order, link_for_order
from .estimates import approve_current
from .forms import BookingForm, ClientLoginForm
from .links import issue_link, resolve_access
from .models import Order, OrderPhoto, Service
from .orders import create_order
from .policies import can_access_order
from .security import client_ip

log = logging.getLogger(__name__)


def _rate_key(request):
    digest = hashlib.sha256(client_ip(request).encode()).hexdigest()[:24]
    return f"booking-rate:{digest}"


def _increment_rate(key, amount=1):
    cache.add(key, 0, 3600)
    try:
        cache.incr(key, amount)
    except ValueError:
        cache.set(key, amount, 3600)


def home(request):
    services = Service.objects.filter(is_active=True)
    if request.method == "POST":
        key = _rate_key(request)
        form = BookingForm(request.POST, request.FILES)
        if cache.get(key, 0) >= 10:
            form.add_error(None, "Слишком много попыток. Подождите час и повторите отправку.")
            return render(request, "service/home.html", {"services": services, "form": form}, status=429)
        files = request.FILES.getlist("photos")
        abusive = bool(request.POST.get("website"))
        if len(files) > 5:
            abusive = True
            form.add_error("photos", "Можно загрузить не более 5 фотографий.")
        if sum(upload.size for upload in files) > 25 * 1024 * 1024:
            abusive = True
            form.add_error("photos", "Суммарный размер файлов превышает 25 МБ.")
        if form.is_valid():
            try:
                signed = form.cleaned_data["submission_key"]
                raw = signing.TimestampSigner(salt="booking").unsign(signed, max_age=7200)
                if not request.session.session_key or not raw.startswith(f"{request.session.session_key}:"):
                    raise ValidationError("Срок формы истёк. Обновите страницу.")
                order, token, created = create_order(
                    form.cleaned_data, files, signed, request.session.session_key
                )
            except (ValidationError, signing.BadSignature, signing.SignatureExpired) as exc:
                _increment_rate(key, 2)
                form.add_error(None, str(exc))
            else:
                _increment_rate(key)
                if not created:
                    return render(request, "service/repeated.html", {"order": order})
                return redirect("success", public_id=order.public_id, token=token)
        elif abusive:
            _increment_rate(key, 2)
    else:
        if not request.session.session_key:
            request.session.create()
        raw = f"{request.session.session_key}:{secrets.token_urlsafe(24)}"
        form = BookingForm(initial={"submission_key": signing.TimestampSigner(salt="booking").sign(raw)})
    return render(request, "service/home.html", {"services": services, "form": form})


def services_list(request):
    return render(request, "service/services.html", {"services": Service.objects.filter(is_active=True)})


def service_detail(request, slug):
    return render(
        request,
        "service/service_detail.html",
        {"item": get_object_or_404(Service, slug=slug, is_active=True)},
    )


def static_page(request, page):
    allowed = {
        "about": "О сервисе",
        "process": "Как мы работаем",
        "cases": "Примеры работ",
        "warranty": "Гарантия",
        "faq": "Вопросы и ответы",
        "contacts": "Контакты",
        "privacy": "Политика конфиденциальности",
        "consent": "Согласие на обработку данных",
    }
    if page not in allowed:
        raise Http404
    return render(request, f"service/{page}.html", {"page_title": allowed[page]})


def exchange_access(request, public_id, token):
    link = resolve_access(public_id, token)
    if not link:
        raise Http404
    establish(request, link)
    return redirect("client_portal")


def success(request, public_id, token):
    link = resolve_access(public_id, token)
    if not link:
        raise Http404
    establish(request, link)
    return render(request, "service/success.html", {"order": link.order})


def client_login(request):
    form = ClientLoginForm(request.POST or None)
    if request.method == "POST":
        key = "client-login:" + _rate_key(request)
        if cache.get(key, 0) >= 8:
            form.add_error(None, "Слишком много попыток. Подождите час и попробуйте снова.")
        elif form.is_valid():
            order = (
                Order.objects.select_related("customer", "vehicle", "service")
                .filter(number__iexact=form.cleaned_data["order_number"])
                .first()
            )
            if order:
                link = (
                    order.access_links.filter(
                        revoked_at__isnull=True,
                        expires_at__gt=timezone.now(),
                    )
                    .order_by("-created_at")
                    .first()
                )
                if not link:
                    token = issue_link(order)
                    link = resolve_access(order.public_id, token)
                establish(request, link)
                cache.delete(key)
                messages.success(request, f"Заявка {order.number} добавлена в ваш кабинет.")
                return redirect("client_portal")
            _increment_rate(key, 2)
            form.add_error(None, "Заявка с таким номером не найдена.")
    return render(request, "service/client_login.html", {"form": form})


@require_POST
def client_logout(request):
    clear_cabinet(request)
    request.session.cycle_key()
    messages.success(request, "Данные кабинета удалены из этого браузера.")
    return redirect("client_login")


def _events_with_unread(request, order, mark_seen=False):
    events = list(order.events.exclude(public_message="").select_related("actor"))
    notifications_key = f"autora_client_notifications:{order.pk}"
    seen_ids = {
        int(value)
        for value in (request.session.get(notifications_key) or [])
        if str(value).isdigit()
    }
    unread_count = 0
    for event in events:
        event.is_unread = event.pk not in seen_ids
        unread_count += int(event.is_unread)
    if mark_seen:
        current_ids = [event.pk for event in events[-100:]]
        if current_ids != request.session.get(notifications_key):
            request.session[notifications_key] = current_ids
    return events, unread_count


def client_portal(request):
    links = cabinet_links(request)
    if not links:
        messages.info(request, "Добавьте заявку по её номеру — регистрация не нужна.")
        return redirect("client_login")
    orders = []
    total_unread = 0
    for link in links:
        _, unread_count = _events_with_unread(request, link.order)
        total_unread += unread_count
        orders.append({"order": link.order, "unread_count": unread_count})
    return render(
        request,
        "service/client_dashboard.html",
        {"orders": orders, "unread_count": total_unread},
    )


def client_order(request, public_id):
    order = link_for_order(request, public_id).order
    stage_index = {
        Order.Status.NEW: 0,
        Order.Status.PENDING: 0,
        Order.Status.BOOKED: 1,
        Order.Status.ACCEPTED: 1,
        Order.Status.DIAGNOSTICS: 2,
        Order.Status.AWAITING_APPROVAL: 2,
        Order.Status.PARTS: 3,
        Order.Status.REPAIR: 3,
        Order.Status.READY: 4,
        Order.Status.DONE: 4,
        Order.Status.CANCELED: 0,
        Order.Status.NO_SHOW: 0,
    }.get(order.status, 0)
    labels = ["Заявка", "Приёмка", "Диагностика", "Работы", "Готово"]
    stages = [
        {
            "number": f"0{index + 1}",
            "label": label,
            "state": "done" if index < stage_index else "current" if index == stage_index else "next",
        }
        for index, label in enumerate(labels)
    ]
    events, unread_count = _events_with_unread(request, order, mark_seen=True)
    return render(
        request,
        "service/track.html",
        {
            "order": order,
            "stages": stages,
            "events": events,
            "unread_count": unread_count,
            "items": order.estimate_items.all(),
        },
    )


@require_POST
def client_forget_order(request, public_id):
    forget_order(request, public_id)
    messages.success(request, "Заявка удалена из этого браузера.")
    return redirect("client_portal")


@require_POST
def client_estimate_approve(request, public_id):
    order = link_for_order(request, public_id).order
    try:
        approve_current(order.pk, request.POST.get("version", ""), "client_portal")
    except (ValidationError, ValueError, TypeError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Смета согласована.")
    return redirect("client_order", public_id=order.public_id)


@require_POST
def client_estimate_approve_legacy(request):
    order = current_link(request).order
    try:
        approve_current(order.pk, request.POST.get("version", ""), "client_portal")
    except (ValidationError, ValueError, TypeError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Смета согласована.")
    return redirect("client_order", public_id=order.public_id)


def private_photo(request, pk):
    photo = get_object_or_404(OrderPhoto.objects.select_related("order"), pk=pk)
    allowed = is_employee(request.user) and can_access_order(request.user, photo.order)
    if not allowed:
        try:
            allowed = link_for_order(request, photo.order.public_id).order_id == photo.order_id
        except Http404:
            allowed = False
    if not allowed:
        raise Http404
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(photo.content_type)
    if not extension:
        raise Http404
    try:
        handle = photo.image.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404 from None
    response = FileResponse(handle, content_type=photo.content_type)
    response["Content-Disposition"] = f'inline; filename="order-photo-{photo.pk}.{extension}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def health(request):
    return JsonResponse({"status": "ok"})


def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("database check failed")
        marker = secrets.token_urlsafe(8)
        cache.set("motor-readiness", marker, 10)
        if cache.get("motor-readiness") != marker:
            raise RuntimeError("cache check failed")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


def error_403(request, exception=None):
    return render(request, "403.html", status=403)


def error_404(request, exception=None):
    return render(request, "404.html", status=404)


def error_500(request):
    return render(request, "500.html", status=500)
