from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .security import client_ip

MANAGER_GROUP = "Менеджеры"
MECHANIC_GROUP = "Мастера"


def is_employee(user):
    return (
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.groups.filter(name__in=[MANAGER_GROUP, MECHANIC_GROUP]).exists())
    )


def is_manager(user):
    return is_employee(user) and (user.is_superuser or user.groups.filter(name=MANAGER_GROUP).exists())


def employee_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/staff/login/?next={request.path}")
        if not is_employee(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def manager_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/staff/login/?next={request.path}")
        if not is_manager(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


class RateLimitedLoginView(LoginView):
    template_name = "service/login.html"

    def _key(self):
        return (
            f"login:{client_ip(self.request)}:{self.request.POST.get('username', '').strip().lower()[:150]}"
        )

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and cache.get(self._key(), 0) >= 5:
            messages.error(request, "Слишком много попыток. Повторите через 15 минут.")
            return self.render_to_response(self.get_context_data(form=self.get_form()), status=429)
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._key()
        cache.set(key, cache.get(key, 0) + 1, 900)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._key())
        return super().form_valid(form)
