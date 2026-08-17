import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} is required")
    return value


def csv_env(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


UNSAFE_MARKERS = (
    "replace-with",
    "replace-me",
    "set-me",
    "set_me",
    "generate",
    "changeme",
    "change-me",
    "your-domain",
    "example.",
    "localhost",
    "127.0.0.1",
)


def reject_unsafe(name, value, minimum_length=1):
    normalized = (value or "").strip().lower()
    if len(normalized) < minimum_length or any(marker in normalized for marker in UNSAFE_MARKERS):
        raise ImproperlyConfigured(f"{name} contains a placeholder or weak value")


ENVIRONMENT = os.getenv("DJANGO_ENV", "production").strip().lower()
if ENVIRONMENT not in {"development", "test", "production"}:
    raise ImproperlyConfigured("DJANGO_ENV must be development, test, or production")
IS_PRODUCTION = ENVIRONMENT == "production"
IS_TEST = ENVIRONMENT == "test"
DEBUG = env_bool("DJANGO_DEBUG", ENVIRONMENT == "development")
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured("DJANGO_DEBUG must be false in production")

SECRET_KEY = (
    required("DJANGO_SECRET_KEY")
    if IS_PRODUCTION
    else os.getenv("DJANGO_SECRET_KEY", "development-only-secret-change-me")
)
if IS_PRODUCTION and len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 characters")
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
ALLOWED_HOSTS = csv_env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver" if not IS_PRODUCTION else "")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS is required")
default_public_url = (
    "https://" + RENDER_EXTERNAL_HOSTNAME
    if IS_PRODUCTION and RENDER_EXTERNAL_HOSTNAME
    else ("http://127.0.0.1:8000" if not IS_PRODUCTION else "")
)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", default_public_url).rstrip("/")
parsed_public_url = urlparse(PUBLIC_BASE_URL)
if IS_PRODUCTION and (
    parsed_public_url.scheme != "https"
    or not parsed_public_url.netloc
    or any(value in PUBLIC_BASE_URL.lower() for value in ("localhost", "127.0.0.1", "example."))
):
    raise ImproperlyConfigured("PUBLIC_BASE_URL must be a real HTTPS URL")

# Keep CSRF configuration aligned with the public URL. This prevents Django's
# admin login from returning a misleading 403 when the app runs behind a proxy.
CSRF_TRUSTED_ORIGINS = csv_env("DJANGO_CSRF_TRUSTED_ORIGINS")
public_origin = (
    f"{parsed_public_url.scheme}://{parsed_public_url.netloc}"
    if parsed_public_url.scheme and parsed_public_url.netloc
    else ""
)
if public_origin and public_origin not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(public_origin)
if not IS_PRODUCTION:
    # Accept both common local hostnames regardless of which one was used in
    # PUBLIC_BASE_URL. This avoids admin-login 403s during portfolio demos.
    for local_origin in (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://0.0.0.0:8000",
        "https://localhost:8000",
        "https://127.0.0.1:8000",
    ):
        if local_origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(local_origin)
if IS_PRODUCTION and not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS is required in production")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "service",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "service.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "service.middleware.LocalDevelopmentOriginMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "service.context_processors.site_settings",
            ]
        },
    }
]

if IS_PRODUCTION or os.getenv("POSTGRES_DB"):
    postgres_sslmode = os.getenv("PGSSLMODE", "require" if IS_PRODUCTION else "prefer").strip()
    if IS_PRODUCTION and postgres_sslmode != "require":
        raise ImproperlyConfigured("PGSSLMODE must be require in production")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": required("POSTGRES_DB"),
            "USER": required("POSTGRES_USER"),
            "PASSWORD": required("POSTGRES_PASSWORD"),
            "HOST": required("POSTGRES_HOST"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60 if IS_PRODUCTION else 0,
            "OPTIONS": {"connect_timeout": 5, "sslmode": postgres_sslmode},
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

REDIS_URL = os.getenv("REDIS_URL", "")
CACHES = (
    {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
    if REDIS_URL
    else {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "motor-local"}}
)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ru"
TIME_ZONE = os.getenv("TIME_ZONE", "Europe/Kyiv")
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "private_media"
MEDIA_URL = "/private-media-disabled/"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": MEDIA_ROOT},
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if IS_PRODUCTION
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "28800"))
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", IS_PRODUCTION)
if IS_PRODUCTION and not SECURE_SSL_REDIRECT:
    raise ImproperlyConfigured("SECURE_SSL_REDIRECT must be true in production")
TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", IS_PRODUCTION)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if TRUST_PROXY_HEADERS else None
USE_X_FORWARDED_HOST = TRUST_PROXY_HEADERS
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if IS_PRODUCTION else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", IS_PRODUCTION)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

EMAIL_ENABLED = env_bool("EMAIL_ENABLED", IS_PRODUCTION)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
if (
    IS_PRODUCTION
    and EMAIL_ENABLED
    and (
        EMAIL_BACKEND.endswith("console.EmailBackend")
        or not os.getenv("EMAIL_HOST")
        or not os.getenv("DEFAULT_FROM_EMAIL")
    )
):
    raise ImproperlyConfigured("Production email configuration is incomplete")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "dev@localhost")
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured("EMAIL_USE_TLS and EMAIL_USE_SSL are mutually exclusive")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CLIENT_LINK_TTL_DAYS = int(os.getenv("CLIENT_LINK_TTL_DAYS", "30"))
DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "730"))
CLIENT_TOKEN_ENCRYPTION_KEYS = csv_env("CLIENT_TOKEN_ENCRYPTION_KEYS")
if not CLIENT_TOKEN_ENCRYPTION_KEYS:
    raise ImproperlyConfigured("CLIENT_TOKEN_ENCRYPTION_KEYS is required")
if IS_PRODUCTION:
    reject_unsafe("DJANGO_SECRET_KEY", SECRET_KEY, 50)
    reject_unsafe("POSTGRES_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""), 16)
    for key in CLIENT_TOKEN_ENCRYPTION_KEYS:
        reject_unsafe("CLIENT_TOKEN_ENCRYPTION_KEYS", key, 24)
        if key == "local-development-encryption-key-change-me":
            raise ImproperlyConfigured("CLIENT_TOKEN_ENCRYPTION_KEYS contains a development value")
    if EMAIL_ENABLED:
        reject_unsafe("EMAIL_HOST_PASSWORD", EMAIL_HOST_PASSWORD, 12)
    for host in ALLOWED_HOSTS:
        reject_unsafe("DJANGO_ALLOWED_HOSTS", host)
    for origin in CSRF_TRUSTED_ORIGINS:
        reject_unsafe("DJANGO_CSRF_TRUSTED_ORIGINS", origin)
    reject_unsafe("PUBLIC_BASE_URL", PUBLIC_BASE_URL)
    if os.getenv("CADDY_HOST"):
        reject_unsafe("CADDY_HOST", os.getenv("CADDY_HOST", ""))
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s request_id=%(request_id)s %(name)s %(message)s"}
    },
    "filters": {"request_id": {"()": "service.middleware.RequestIdFilter"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard", "filters": ["request_id"]}
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
