from django.http import Http404
from django.utils import timezone

from .models import ClientAccess

SESSION_KEY = "motor_client_access"
CABINET_KEY = "autora_client_orders"
MAX_CABINET_ORDERS = 20


def _payload(link):
    return {"id": link.pk, "version": str(link.session_version)}


def establish(request, link):
    """Remember an order in this browser without creating a user account."""
    request.session.cycle_key()
    request.session[SESSION_KEY] = _payload(link)
    cabinet = dict(request.session.get(CABINET_KEY) or {})
    cabinet[str(link.order.public_id)] = _payload(link)
    if len(cabinet) > MAX_CABINET_ORDERS:
        cabinet = dict(list(cabinet.items())[-MAX_CABINET_ORDERS:])
    request.session[CABINET_KEY] = cabinet
    seconds = max(1, int((link.expires_at - timezone.now()).total_seconds()))
    request.session.set_expiry(seconds)


def _valid_link(data, public_id=None):
    if not data:
        return None
    try:
        queryset = ClientAccess.objects.select_related(
            "order", "order__customer", "order__vehicle", "order__service"
        ).filter(
            pk=data.get("id"),
            session_version=data.get("version"),
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        if public_id is not None:
            queryset = queryset.filter(order__public_id=public_id)
        return queryset.first()
    except (ValueError, TypeError, AttributeError):
        return None


def current_link(request):
    link = _valid_link(request.session.get(SESSION_KEY))
    if not link:
        request.session.pop(SESSION_KEY, None)
        raise Http404
    return link


def cabinet_links(request):
    cabinet = dict(request.session.get(CABINET_KEY) or {})
    valid = []
    cleaned = {}
    for public_id, data in cabinet.items():
        link = _valid_link(data, public_id)
        if link:
            cleaned[public_id] = data
            valid.append(link)
    if cleaned != cabinet:
        request.session[CABINET_KEY] = cleaned
    return sorted(valid, key=lambda item: item.order.updated_at, reverse=True)


def link_for_order(request, public_id):
    cabinet = request.session.get(CABINET_KEY) or {}
    link = _valid_link(cabinet.get(str(public_id)), public_id)
    if not link:
        current = _valid_link(request.session.get(SESSION_KEY), public_id)
        if current:
            establish(request, current)
            return current
        raise Http404
    request.session[SESSION_KEY] = _payload(link)
    return link


def forget_order(request, public_id):
    cabinet = dict(request.session.get(CABINET_KEY) or {})
    cabinet.pop(str(public_id), None)
    request.session[CABINET_KEY] = cabinet
    current = request.session.get(SESSION_KEY) or {}
    link = _valid_link(current)
    if link and str(link.order.public_id) == str(public_id):
        request.session.pop(SESSION_KEY, None)


def clear_cabinet(request):
    request.session.pop(SESSION_KEY, None)
    request.session.pop(CABINET_KEY, None)
    for key in list(request.session.keys()):
        if key.startswith("autora_client_notifications:"):
            request.session.pop(key, None)
