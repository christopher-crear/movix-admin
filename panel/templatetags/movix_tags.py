from urllib.parse import quote

from django import template
from django.conf import settings


register = template.Library()


@register.filter
def file_name(value):
    if not value:
        return "Sin archivo"
    return str(value).split("?")[0].rstrip("/").split("/")[-1]


@register.filter
def stars(value):
    try:
        count = max(0, min(5, round(float(value))))
    except (TypeError, ValueError):
        count = 0
    return "★" * count + "☆" * (5 - count)


@register.filter
def role_label(value):
    return "Transportista" if str(value).lower() in {"driver", "conductor", "transportista"} else "Usuario"


@register.filter
def profile_photo_url(profile):
    value = str(getattr(profile, "profile_photo_url", "") or getattr(profile, "avatar_url", "") or "").strip()
    if not value:
        return ""
    if value.startswith(("https://", "http://")):
        return value
    if value.startswith("storage://"):
        bucket_path = value.removeprefix("storage://")
        if bucket_path.startswith(f"{settings.SUPABASE_PUBLIC_BUCKET}/"):
            return f"{settings.SUPABASE_URL}/storage/v1/object/public/{quote(bucket_path, safe='/')}"
    return ""


@register.filter
def is_pdf(value):
    return str(value or "").split("?", 1)[0].lower().endswith(".pdf")
