import json
import logging
import random
import re
import urllib.error
import urllib.request
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .links import decrypt_token
from .models import NotificationLog

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 6
LOCK_TIMEOUT = timedelta(minutes=10)


def sanitize_error(error):
    text = str(error).replace("\n", " ").replace("\r", " ")
    secrets = (
        settings.TELEGRAM_BOT_TOKEN,
        settings.EMAIL_HOST_PASSWORD,
        *settings.CLIENT_TOKEN_ENCRYPTION_KEYS,
    )
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"https?://\S+", "[url-redacted]", text)
    text = re.sub(r"(?i)(bearer\s+)?[A-Za-z0-9_-]{32,}", "[token-redacted]", text)
    return text[:300]


def queue(order, event_type, event_id=None):
    event_id = event_id or uuid.uuid4()
    channels = []
    if settings.EMAIL_ENABLED and order.customer.email:
        channels.append((NotificationLog.Channel.EMAIL, order.customer.email[:2] + "***"))
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
        channels.append((NotificationLog.Channel.TELEGRAM, "service-chat"))
    for channel, hint in channels:
        NotificationLog.objects.get_or_create(
            dedupe_key=f"{order.pk}:{event_id}:{channel}",
            defaults={
                "order": order,
                "event_id": event_id,
                "channel": channel,
                "event_type": event_type,
                "recipient_hint": hint,
                "next_attempt_at": timezone.now(),
            },
        )


def queue_on_commit(order, event_type, event_id=None):
    stable_event_id = event_id or uuid.uuid4()
    transaction.on_commit(lambda: queue(order, event_type, stable_event_id))


def message_for(notification):
    return {
        "order_created": "Заявка получена.",
        "schedule_changed": "Время визита обновлено.",
        "status_ready": "Автомобиль готов к выдаче.",
        "link_reissued": "Выпущена новая защищённая ссылка.",
        "estimate_approved": "Предварительная смета согласована.",
    }.get(notification.event_type, f"Статус: {notification.order.get_status_display()}.")


def tracking_url(order):
    link = (
        order.access_links.filter(revoked_at__isnull=True, expires_at__gt=timezone.now())
        .order_by("-created_at")
        .first()
    )
    token = decrypt_token(link) if link else None
    if not token:
        return ""
    return settings.PUBLIC_BASE_URL + reverse("client_exchange", args=[order.public_id, token])


def claim(worker_id):
    now = timezone.now()
    with transaction.atomic():
        NotificationLog.objects.filter(
            status=NotificationLog.Status.PROCESSING,
            locked_at__lt=now - LOCK_TIMEOUT,
        ).update(
            status=NotificationLog.Status.PENDING,
            worker_id="",
            locked_at=None,
            next_attempt_at=now,
        )
        queryset = NotificationLog.objects.select_for_update(
            skip_locked=connection.features.has_select_for_update_skip_locked
        )
        item = (
            queryset.select_related("order", "order__customer")
            .filter(
                status=NotificationLog.Status.PENDING,
                next_attempt_at__lte=now,
                failed_permanently_at__isnull=True,
            )
            .order_by("next_attempt_at")
            .first()
        )
        if not item:
            return None
        item.status = NotificationLog.Status.PROCESSING
        item.locked_at = now
        item.worker_id = worker_id
        item.attempts += 1
        item.save(update_fields=["status", "locked_at", "worker_id", "attempts"])
        return item.pk


def deliver(item):
    text = message_for(item)
    url = tracking_url(item.order)
    context = {
        "order": item.order,
        "message": text,
        "tracking_url": url,
        "expires_days": settings.CLIENT_LINK_TTL_DAYS,
    }
    if item.channel == NotificationLog.Channel.EMAIL:
        mail = EmailMultiAlternatives(
            f"AUTORA · {item.order.number}",
            render_to_string("email/order.txt", context),
            settings.DEFAULT_FROM_EMAIL,
            [item.order.customer.email],
        )
        mail.attach_alternative(render_to_string("email/order.html", context), "text/html")
        mail.send()
        return
    payload = json.dumps(
        {"chat_id": settings.TELEGRAM_CHAT_ID, "text": f"Заказ {item.order.number}. {text}"},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.telegram.org/bot" + settings.TELEGRAM_BOT_TOKEN + "/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Telegram HTTP {response.status}")


def process_one(worker_id):
    pk = claim(worker_id)
    if not pk:
        return False
    item = NotificationLog.objects.select_related("order", "order__customer").get(pk=pk)
    try:
        deliver(item)
        error = ""
    except Exception as exc:
        error = sanitize_error(exc)
        logger.warning("Notification delivery failed: %s", error)
    with transaction.atomic():
        current = NotificationLog.objects.select_for_update().get(
            pk=pk, worker_id=worker_id, status=NotificationLog.Status.PROCESSING
        )
        current.locked_at = None
        current.worker_id = ""
        if not error:
            current.status = NotificationLog.Status.SENT
            current.sent_at = timezone.now()
            current.last_error = ""
        elif current.attempts >= MAX_ATTEMPTS:
            current.status = NotificationLog.Status.FAILED
            current.failed_permanently_at = timezone.now()
            current.last_error = error
        else:
            current.status = NotificationLog.Status.PENDING
            current.last_error = error
            delay = min(2**current.attempts, 240) + random.randint(0, 30)
            current.next_attempt_at = timezone.now() + timedelta(minutes=delay)
        current.save(
            update_fields=[
                "status",
                "sent_at",
                "last_error",
                "next_attempt_at",
                "locked_at",
                "worker_id",
                "failed_permanently_at",
            ]
        )
    return True


def process_batch(limit=50, worker_id=None):
    limit = max(1, min(int(limit), 500))
    worker_id = worker_id or f"worker-{uuid.uuid4()}"
    processed = 0
    while processed < limit and process_one(worker_id):
        processed += 1
    return processed
