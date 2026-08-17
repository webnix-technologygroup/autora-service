from django.http import Http404
from django.utils import timezone

from .models import ClientAccess

SESSION_KEY = "motor_client_access"


def establish(request, link):
    request.session.cycle_key()
    request.session[SESSION_KEY] = {"id": link.pk, "version": str(link.session_version)}
    seconds = max(1, int((link.expires_at - timezone.now()).total_seconds()))
    request.session.set_expiry(seconds)


def current_link(request):
    data = request.session.get(SESSION_KEY) or {}
    try:
        link = ClientAccess.objects.select_related(
            "order", "order__customer", "order__vehicle", "order__service"
        ).get(
            pk=data.get("id"),
            session_version=data.get("version"),
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
    except (ClientAccess.DoesNotExist, ValueError, TypeError):
        request.session.pop(SESSION_KEY, None)
        raise Http404 from None
    return link
