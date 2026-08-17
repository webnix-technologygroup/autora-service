import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone


def normalize_phone(value: str) -> str:
    value = re.sub(r"[^0-9+]", "", value.strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    if not value.startswith("+"):
        value = "+" + value
    if not re.fullmatch(r"\+[1-9]\d{8,14}", value):
        raise ValidationError("Введите телефон в международном формате, например +380501234567.")
    return value


def normalize_plate(value: str) -> str:
    return re.sub(r"[^A-ZА-ЯІЇЄ0-9]", "", value.upper().strip())


def validate_vin(value: str) -> str:
    value = value.upper().strip()
    if value and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value):
        raise ValidationError("VIN должен содержать 17 допустимых символов.")
    return value


def validate_requested_datetime(day, tm=None):
    today = timezone.localdate()
    if day < today:
        raise ValidationError("Желаемая дата не может быть в прошлом.")
    if day > today + timedelta(days=180):
        raise ValidationError("Выберите дату в пределах 180 дней.")
    if day.weekday() == 6:
        raise ValidationError("В воскресенье сервис закрыт.")
    if tm and not (8 <= tm.hour < 20):
        raise ValidationError("Желаемое время должно быть с 08:00 до 20:00.")
