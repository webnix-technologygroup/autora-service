import io
import secrets
import warnings
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.models.signals import post_delete
from django.dispatch import receiver
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import OrderPhoto

ALLOWED = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 24_000_000


def normalize_image(upload):
    if not upload or upload.size == 0:
        raise ValidationError("Пустой файл.")
    if upload.size > MAX_BYTES:
        raise ValidationError("Фотография больше 5 МБ.")
    try:
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        upload.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                source.verify()
        upload.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in ALLOWED:
                    raise ValidationError("Разрешены JPEG, PNG и WEBP.")
                extension, mime = ALLOWED[source.format]
                claimed = Path(upload.name).suffix.lower()
                valid_extensions = {".jpg", ".jpeg"} if source.format == "JPEG" else {extension}
                if claimed not in valid_extensions:
                    raise ValidationError("Расширение не соответствует изображению.")
                if source.width * source.height > MAX_PIXELS:
                    raise ValidationError("Слишком большое разрешение изображения.")
                image = ImageOps.exif_transpose(source)
                if image.width > 2400 or image.height > 2400:
                    image.thumbnail((2400, 2400))
                if source.format == "JPEG":
                    image = image.convert("RGB")
                output = io.BytesIO()
                options = (
                    {"quality": 86, "optimize": True}
                    if source.format in {"JPEG", "WEBP"}
                    else {"optimize": True}
                )
                image.save(output, format=source.format, **options)
                safe_name = f"{secrets.token_hex(16)}{extension}"
                return ContentFile(output.getvalue(), name=safe_name), mime, Path(upload.name).name[:120]
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError("Повреждённое или опасное изображение.") from exc


@receiver(post_delete, sender=OrderPhoto)
def delete_photo_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
