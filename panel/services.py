import json
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.utils import timezone
from django.utils.text import slugify

from .models import AuditLog, DeviceToken


ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


def _supabase_headers(content_type=None):
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise ValidationError("Configura SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en el archivo .env.")
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _storage_error(response, action):
    try:
        payload = response.json()
        detail = payload.get("message") or payload.get("error") or payload.get("statusCode")
    except (ValueError, AttributeError):
        detail = response.text
    detail = str(detail or "respuesta vacía")[:280]
    if response.status_code in {401, 403}:
        return ValidationError(
            "Supabase rechazó la carga. Verifica que SUPABASE_SERVICE_ROLE_KEY sea una clave "
            f"secreta del backend y no la clave pública. Detalle: {detail}"
        )
    if response.status_code == 413:
        return ValidationError("Supabase rechazó el archivo porque supera el tamaño permitido.")
    return ValidationError(f"No se pudo {action} en Supabase Storage ({response.status_code}): {detail}")


def ensure_storage_bucket(bucket, public=False, images_only=False):
    """Crea el bucket cuando el SQL aún no se ha ejecutado o fue incompleto."""
    cache_key = f"movix-storage-bucket:{bucket}"
    if cache.get(cache_key):
        return
    endpoint = f"{settings.SUPABASE_URL}/storage/v1/bucket/{quote(bucket, safe='')}"
    try:
        response = requests.get(endpoint, headers=_supabase_headers(), timeout=(8, 20))
        if response.status_code == 404:
            allowed = ["image/jpeg", "image/png", "image/webp"]
            if not images_only:
                allowed.append("application/pdf")
            response = requests.post(
                f"{settings.SUPABASE_URL}/storage/v1/bucket",
                headers=_supabase_headers("application/json"),
                json={
                    "id": bucket,
                    "name": bucket,
                    "public": public,
                    "file_size_limit": settings.MAX_UPLOAD_MB * 1024 * 1024,
                    "allowed_mime_types": allowed,
                },
                timeout=(8, 25),
            )
            if response.status_code not in {200, 201}:
                raise _storage_error(response, f"crear el bucket {bucket}")
        elif response.status_code != 200:
            raise _storage_error(response, f"comprobar el bucket {bucket}")
    except requests.RequestException as exc:
        raise ValidationError(f"No se pudo conectar con Supabase Storage: {exc}") from exc
    cache.set(cache_key, True, 300)


def validate_upload(uploaded_file, images_only=False):
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    content_type = uploaded_file.content_type or mimetypes.guess_type(uploaded_file.name)[0]
    allowed = {"image/jpeg", "image/png", "image/webp"} if images_only else ALLOWED_MIME_TYPES
    if uploaded_file.size > limit:
        raise ValidationError(f"El archivo supera el máximo de {settings.MAX_UPLOAD_MB} MB.")
    if content_type not in allowed:
        raise ValidationError("Formato no permitido. Usa PNG, JPG, WEBP o PDF.")
    return content_type


def upload_to_supabase(uploaded_file, folder, public=False, images_only=False):
    content_type = validate_upload(uploaded_file, images_only=images_only)
    suffix = Path(uploaded_file.name).suffix.lower()
    safe_name = slugify(Path(uploaded_file.name).stem)[:60] or "archivo"
    object_path = f"{folder.strip('/')}/{uuid.uuid4().hex}-{safe_name}{suffix}"
    bucket = settings.SUPABASE_PUBLIC_BUCKET if public else settings.SUPABASE_PRIVATE_BUCKET
    ensure_storage_bucket(bucket, public=public, images_only=images_only)
    endpoint = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{quote(object_path, safe='/')}"
    try:
        response = requests.post(
            endpoint,
            headers={**_supabase_headers(content_type), "x-upsert": "false", "cache-control": "3600"},
            data=uploaded_file.read(),
            timeout=(10, 60),
        )
    except requests.RequestException as exc:
        raise ValidationError(f"No se pudo conectar con Supabase al subir el archivo: {exc}") from exc
    if response.status_code not in {200, 201}:
        raise _storage_error(response, "subir el archivo")
    if public:
        return f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{quote(object_path, safe='/')}"
    return f"storage://{bucket}/{object_path}"


def resolve_media_url(value, expires=900):
    if not value:
        return ""
    if not value.startswith("storage://"):
        return value
    bucket_and_path = value.removeprefix("storage://")
    bucket, object_path = bucket_and_path.split("/", 1)
    endpoint = f"{settings.SUPABASE_URL}/storage/v1/object/sign/{bucket}/{quote(object_path, safe='/')}"
    try:
        response = requests.post(endpoint, headers=_supabase_headers("application/json"), json={"expiresIn": expires}, timeout=(8, 25))
    except requests.RequestException:
        return ""
    if response.status_code not in {200, 201}:
        return ""
    signed = response.json().get("signedURL") or response.json().get("signedUrl") or ""
    if signed.startswith("http"):
        return signed
    return f"{settings.SUPABASE_URL}/storage/v1{signed}"


def delete_storage_object(value):
    if not value:
        return
    if value.startswith("storage://"):
        bucket_and_path = value.removeprefix("storage://")
    else:
        public_prefix = f"{settings.SUPABASE_URL}/storage/v1/object/public/"
        if not value.startswith(public_prefix):
            return
        bucket_and_path = value.removeprefix(public_prefix).split("?", 1)[0]
    bucket, object_path = bucket_and_path.split("/", 1)
    endpoint = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}"
    try:
        requests.delete(endpoint, headers=_supabase_headers("application/json"), json={"prefixes": [object_path]}, timeout=(8, 25))
    except requests.RequestException:
        pass


def create_supabase_auth_user(email, password, metadata):
    endpoint = f"{settings.SUPABASE_URL}/auth/v1/admin/users"
    response = requests.post(
        endpoint,
        headers=_supabase_headers("application/json"),
        json={"email": email, "password": password, "email_confirm": True, "user_metadata": metadata},
        timeout=30,
    )
    if response.status_code not in {200, 201}:
        raise ValidationError(f"No se pudo crear la cuenta en Supabase Auth: {response.text[:300]}")
    payload = response.json()
    user_id = payload.get("id") or (payload.get("user") or {}).get("id")
    if not user_id:
        raise ValidationError("Supabase Auth creó una respuesta sin identificador de usuario.")
    return user_id


def delete_supabase_auth_user(user_id):
    endpoint = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    response = requests.delete(endpoint, headers=_supabase_headers("application/json"), timeout=30)
    if response.status_code not in {200, 204}:
        raise ValidationError(f"No se pudo eliminar la cuenta de Supabase Auth: {response.text[:300]}")


def send_push_notifications(tokens, title, body, data=None):
    tokens = [token for token in tokens if token]
    if not tokens or not settings.FIREBASE_CREDENTIALS_JSON:
        return 0, "Push omitido: no hay tokens activos o credenciales Firebase."
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging

        try:
            firebase_admin.get_app()
        except ValueError:
            credentials_value = settings.FIREBASE_CREDENTIALS_JSON
            if credentials_value.strip().startswith("{"):
                certificate = credentials.Certificate(json.loads(credentials_value))
            else:
                certificate = credentials.Certificate(credentials_value)
            firebase_admin.initialize_app(certificate)

        sent = 0
        for index in range(0, len(tokens), 500):
            message = messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                data={str(k): str(v) for k, v in (data or {}).items()},
                tokens=tokens[index:index + 500],
            )
            response = messaging.send_each_for_multicast(message)
            sent += response.success_count
        return sent, ""
    except Exception as exc:  # El historial conserva el error sin perder la notificación interna.
        return 0, str(exc)[:500]


def active_tokens_for_users(user_ids):
    return list(DeviceToken.objects.filter(user_id__in=user_ids, is_active=True).values_list("token", flat=True))


def audit(request, action, entity_type, description, entity_id=None, metadata=None):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    try:
        AuditLog.objects.create(
            id=uuid.uuid4(),
            admin_username=request.user.username,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            description=description,
            metadata=metadata or {},
            ip_address=ip_address,
            created_at=timezone.now(),
        )
        cache.delete("movix-top-activity")
    except DatabaseError:
        pass


def is_safe_media_url(value):
    if value.startswith("storage://"):
        return True
    parsed = urlparse(value)
    if parsed.scheme != "https":
        return False
    allowed = {urlparse(settings.SUPABASE_URL).hostname, "res.cloudinary.com"}
    return parsed.hostname in allowed
