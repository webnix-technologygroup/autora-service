import base64
import hashlib
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ClientAccess, OrderEvent


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _fernet(version=1):
    raw = settings.CLIENT_TOKEN_ENCRYPTION_KEYS[version - 1].encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))


def encrypt_token(token, version=1):
    return _fernet(version).encrypt(token.encode()).decode()


def decrypt_token(link):
    try:
        return _fernet(link.encryption_key_version).decrypt(link.token_ciphertext.encode()).decode()
    except (InvalidToken, IndexError):
        return None


def issue_link(order, actor=None):
    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        order.access_links.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        ClientAccess.objects.create(
            order=order,
            token_hash=token_hash(token),
            token_ciphertext=encrypt_token(token),
            encryption_key_version=1,
            expires_at=timezone.now() + timedelta(days=settings.CLIENT_LINK_TTL_DAYS),
            created_by=actor,
        )
        OrderEvent.objects.create(
            order=order,
            kind=OrderEvent.Kind.LINK,
            actor=actor,
            internal_message="Клиентская ссылка выпущена/перевыпущена",
        )
    return token


def resolve_access(public_id, token):
    try:
        return ClientAccess.objects.select_related(
            "order", "order__customer", "order__vehicle", "order__service"
        ).get(
            order__public_id=public_id,
            token_hash=token_hash(token),
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
    except ClientAccess.DoesNotExist:
        return None
