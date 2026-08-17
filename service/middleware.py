import contextvars
import logging
import re
import uuid

_request_id = contextvars.ContextVar("request_id", default="-")
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]"}


class LocalDevelopmentOriginMiddleware:
    """Allow embedded local preview browsers while retaining CSRF tokens.

    Some IDE preview panes send the literal header ``Origin: null``. Django
    cannot compare that value with an http(s) trusted origin, so it rejects a
    valid admin form before checking its token. Only in DEBUG and only for a
    loopback host, discard that unusable header. CsrfViewMiddleware still runs
    immediately afterwards and still requires a valid CSRF cookie/form token.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        hostname = request.get_host().partition(":")[0].lower()
        if settings.DEBUG and hostname in LOCAL_HOSTS and request.META.get("HTTP_ORIGIN") == "null":
            request.META.pop("HTTP_ORIGIN", None)
        return self.get_response(request)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = _request_id.get()
        return True


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get("X-Request-ID", "")
        request.request_id = supplied if SAFE_ID.fullmatch(supplied) else str(uuid.uuid4())
        token = _request_id.set(request.request_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request.request_id
            response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
            response["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'self'; form-action 'self'"
            )
            response["Referrer-Policy"] = "no-referrer"
            response["X-Content-Type-Options"] = "nosniff"
            if request.path.startswith(
                ("/staff/", "/access/", "/success/", "/portal/", "/private/", "/admin/")
            ):
                response["Cache-Control"] = "private, no-store, max-age=0"
            return response
        finally:
            _request_id.reset(token)
