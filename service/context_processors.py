from types import SimpleNamespace

from django.db import DatabaseError

from .models import SiteSettings

FALLBACK = SimpleNamespace(name="AUTORA", phone="", email="", address="", working_hours="", about="Автосервис")


def site_settings(request):
    try:
        site = SiteSettings.objects.first() or FALLBACK
    except DatabaseError:
        site = FALLBACK
    return {"site": site}
