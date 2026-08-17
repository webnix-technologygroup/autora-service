import hashlib

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .files import normalize_image
from .links import issue_link
from .models import Customer, Order, OrderEvent, OrderPhoto, Submission, Vehicle
from .notifications import queue_on_commit
from .policies import allowed_transitions


def find_vehicle(customer, data):
    queryset = customer.vehicles.all()
    for key in ("vin", "plate"):
        if data.get(key):
            found = queryset.filter(**{key: data[key]}).first()
            if found:
                return found
    found = queryset.filter(
        make__iexact=data["make"], model__iexact=data["model"], year=data.get("year")
    ).first()
    if found:
        return found
    vehicle = Vehicle(
        customer=customer,
        make=data["make"],
        model=data["model"],
        year=data.get("year"),
        plate=data.get("plate", ""),
        vin=data.get("vin", ""),
    )
    vehicle.full_clean()
    vehicle.save()
    return vehicle


def create_order(data, files, submission_key, session_key=""):
    key_hash = hashlib.sha256(submission_key.encode()).hexdigest()
    normalized = [normalize_image(upload) for upload in files]
    with transaction.atomic():
        submission, created = Submission.objects.select_for_update().get_or_create(
            key_hash=key_hash,
            defaults={
                "session_key": session_key,
                "expires_at": timezone.now() + timezone.timedelta(hours=2),
            },
        )
        if submission.session_key != session_key or submission.expires_at <= timezone.now():
            raise ValidationError("Срок формы истёк. Обновите страницу.")
        if not created and submission.order_id:
            return submission.order, None, False
        customer, customer_created = Customer.objects.get_or_create(
            phone=data["phone"], defaults={"name": data["name"], "email": data.get("email", "")}
        )
        if not customer_created:
            customer.name = data["name"]
            customer.email = data.get("email", "")
            customer.full_clean()
            customer.save(update_fields=["name", "email"])
        vehicle = find_vehicle(customer, data)
        for _ in range(5):
            try:
                order = Order(
                    number=Order.new_number(),
                    customer=customer,
                    vehicle=vehicle,
                    service=data["service"],
                    service_name=data["service"].name,
                    service_price_from=data["service"].price_from,
                    problem=data["problem"],
                    desired_date=data["desired_date"],
                    desired_time=data.get("desired_time"),
                )
                order.full_clean()
                order.save()
                break
            except IntegrityError:
                continue
        else:
            raise RuntimeError("Не удалось создать уникальный номер")
        for content, mime, original in normalized:
            OrderPhoto.objects.create(
                order=order,
                image=content,
                original_name=original,
                content_type=mime,
                size=content.size,
            )
        OrderEvent.objects.create(
            order=order,
            kind=OrderEvent.Kind.CREATED,
            new_status=order.status,
            public_message="Заявка получена. Ожидайте подтверждения менеджера.",
        )
        submission.order = order
        submission.save(update_fields=["order"])
        token = issue_link(order)
        queue_on_commit(order, "order_created")
        return order, token, True


def transition(order, new_status, actor: User, public_message="", internal_message="", expected_status=None):
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if expected_status and locked.status != expected_status:
            raise ValidationError("Статус уже изменился. Обновите страницу.")
        if new_status not in allowed_transitions(actor, locked):
            raise PermissionDenied("Переход недоступен для вашей роли или требует согласования сметы.")
        old = locked.status
        locked.status = new_status
        locked.save(update_fields=["status", "updated_at"])
        OrderEvent.objects.create(
            order=locked,
            kind=OrderEvent.Kind.STATUS,
            old_status=old,
            new_status=new_status,
            public_message=public_message or locked.get_status_display(),
            internal_message=internal_message,
            actor=actor,
        )
        queue_on_commit(locked, f"status_{new_status}")
        return locked
