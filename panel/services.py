import base64
import json
import mimetypes
import uuid
from html import escape as html_escape
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import DatabaseError, connection
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


def _supabase_auth_headers(access_token=""):
    """Cabeceras para Supabase Auth sin exponer la service role al navegador."""
    api_key = settings.SUPABASE_ANON_KEY or settings.SUPABASE_SERVICE_ROLE_KEY
    if not settings.SUPABASE_URL or not api_key:
        raise ValidationError("Configura SUPABASE_URL y SUPABASE_ANON_KEY para habilitar el acceso de usuarios.")
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def supabase_password_sign_in(email, password):
    """Autentica una cuenta real de Supabase con correo y contraseña."""
    try:
        response = requests.post(
            f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers=_supabase_auth_headers(),
            json={"email": email, "password": password},
            timeout=(8, 25),
        )
    except requests.RequestException as exc:
        raise ValidationError(f"No se pudo conectar con Supabase Auth: {exc}") from exc
    if response.status_code != 200:
        try:
            detail = response.json().get("msg") or response.json().get("error_description") or response.json().get("message")
        except ValueError:
            detail = response.text
        raise ValidationError(str(detail or "Correo o contraseña incorrectos.")[:240])
    return response.json()


def supabase_user_from_token(access_token):
    """Valida en Supabase un token devuelto por Google o por el login normal."""
    try:
        response = requests.get(
            f"{settings.SUPABASE_URL}/auth/v1/user",
            headers=_supabase_auth_headers(access_token),
            timeout=(8, 25),
        )
    except requests.RequestException as exc:
        raise ValidationError(f"No se pudo validar la sesión con Supabase: {exc}") from exc
    if response.status_code != 200:
        raise ValidationError("La sesión de Supabase no es válida o ya caducó.")
    return response.json()


def supabase_update_password(access_token, new_password):
    """Actualiza la contraseña de la cuenta autenticada, nunca la de otro usuario."""
    try:
        response = requests.put(
            f"{settings.SUPABASE_URL}/auth/v1/user",
            headers=_supabase_auth_headers(access_token),
            json={"password": new_password},
            timeout=(8, 25),
        )
    except requests.RequestException as exc:
        raise ValidationError(f"No se pudo conectar con Supabase para cambiar la contraseña: {exc}") from exc
    if response.status_code != 200:
        try:
            detail = response.json().get("msg") or response.json().get("message")
        except ValueError:
            detail = response.text
        raise ValidationError(str(detail or "Supabase rechazó la nueva contraseña.")[:240])
    return response.json()


def supabase_admin_update_password(user_id, new_password):
    """Restablece la clave de una cuenta concreta desde el backend seguro."""
    try:
        response = requests.put(
            f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
            headers=_supabase_headers("application/json"),
            json={"password": new_password},
            timeout=(8, 25),
        )
    except requests.RequestException as exc:
        raise ValidationError(f"No se pudo conectar con Supabase para restablecer la contraseña: {exc}") from exc
    if response.status_code != 200:
        try:
            detail = response.json().get("msg") or response.json().get("message")
        except ValueError:
            detail = response.text
        raise ValidationError(str(detail or "Supabase rechazó la nueva contraseña.")[:240])
    return response.json()


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


def _clean_media_value(value):
    """Normaliza valores guardados por Flutter, Django o la API de Storage."""
    return str(value or "").strip().strip('"').replace("\\", "/")


def _configured_buckets(preferred_buckets=None):
    values = [*(preferred_buckets or ()), settings.SUPABASE_PRIVATE_BUCKET, settings.SUPABASE_PUBLIC_BUCKET]
    return list(dict.fromkeys(bucket for bucket in values if bucket))


def _storage_reference(value):
    """Devuelve (bucket, objeto, es_publico, ya_firmado) cuando puede extraerlos."""
    value = _clean_media_value(value)
    if value.startswith("storage://"):
        remainder = value.removeprefix("storage://").lstrip("/")
        if "/" not in remainder:
            return None
        bucket, object_path = remainder.split("/", 1)
        return bucket, unquote(object_path), False, False

    parsed = urlparse(value)
    path = unquote(parsed.path or value.split("?", 1)[0])
    marker = "/storage/v1/object/"
    if marker not in path:
        return None
    remainder = path.split(marker, 1)[1].lstrip("/")
    mode = ""
    for prefix in ("public/", "authenticated/", "sign/"):
        if remainder.startswith(prefix):
            mode = prefix.rstrip("/")
            remainder = remainder[len(prefix):]
            break
    if "/" not in remainder:
        return None
    bucket, object_path = remainder.split("/", 1)
    return bucket, object_path, mode == "public", mode == "sign" and bool(parsed.query)


def _signed_storage_url(bucket, object_path, expires):
    if not bucket or not object_path:
        return ""
    cache_key = f"movix-signed-media:{bucket}:{object_path}:{expires}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    endpoint = f"{settings.SUPABASE_URL}/storage/v1/object/sign/{bucket}/{quote(object_path, safe='/')}"
    try:
        response = requests.post(endpoint, headers=_supabase_headers("application/json"), json={"expiresIn": expires}, timeout=(8, 25))
    except (requests.RequestException, ValidationError):
        return ""
    if response.status_code not in {200, 201}:
        return ""
    signed = response.json().get("signedURL") or response.json().get("signedUrl") or ""
    if signed.startswith("http"):
        result = signed
    elif signed.startswith("/storage/v1/"):
        result = f"{settings.SUPABASE_URL}{signed}"
    elif signed.startswith("/object/"):
        result = f"{settings.SUPABASE_URL}/storage/v1{signed}"
    else:
        result = f"{settings.SUPABASE_URL}/storage/v1/{signed.lstrip('/')}"
    cache.set(cache_key, result, max(30, min(expires - 15, 600)))
    return result


def _find_storage_objects(value):
    """Busca el objeto real y si su bucket es público.

    La aplicación móvil usa tanto `movix-documents` como `profile-media` y
    `movix-public`. No se debe asumir el bucket basándose solamente en el campo.
    """
    value = _clean_media_value(value)
    path = unquote(urlparse(value).path or value).split("?", 1)[0].lstrip("/")
    reference = _storage_reference(value)
    if reference:
        path = reference[1]
    basename = path.rsplit("/", 1)[-1]
    if not basename:
        return []
    cache_key = f"movix-storage-lookup:{path}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    suffix = f"/{basename}"
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.bucket_id, o.name, COALESCE(b.public, false)
                FROM storage.objects o
                LEFT JOIN storage.buckets b ON b.id = o.bucket_id
                WHERE o.name = %s
                   OR o.name = %s
                   OR right(o.name, length(%s)) = %s
                ORDER BY CASE WHEN o.name = %s THEN 0 WHEN o.name = %s THEN 1 ELSE 2 END,
                         o.updated_at DESC NULLS LAST
                LIMIT 8
                """,
                [path, basename, suffix, suffix, path, basename],
            )
            matches = [(str(row[0]), str(row[1]), bool(row[2])) for row in cursor.fetchall()]
    except DatabaseError:
        matches = []
    cache.set(cache_key, matches, 300)
    return matches


def resolve_media_url(value, expires=900, preferred_buckets=None):
    """Resuelve URLs completas, storage:// y rutas crudas guardadas por la app móvil."""
    value = _clean_media_value(value)
    if not value:
        return ""

    parsed = urlparse(value)
    supabase_host = urlparse(settings.SUPABASE_URL).hostname
    if parsed.scheme == "https" and parsed.hostname not in {supabase_host}:
        return value

    reference = _storage_reference(value)
    if reference:
        bucket, object_path, is_public, is_signed = reference
        # Los buckets públicos no necesitan firmarse. Esto permite mostrar las
        # imágenes históricas de `profile-media` aunque la URL se haya guardado
        # antes de que existiera el panel administrativo.
        if is_public:
            if parsed.scheme == "https":
                return value
            return f"{settings.SUPABASE_URL}/storage/v1/object/public/{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
        signed = _signed_storage_url(bucket, object_path, expires)
        if signed:
            return signed
        if is_signed:
            return value
        return ""

    if parsed.scheme == "https":
        return value

    raw_path = unquote(value.split("?", 1)[0]).lstrip("/")
    candidates = _find_storage_objects(raw_path)
    configured = _configured_buckets(preferred_buckets)
    if "/" in raw_path and raw_path.split("/", 1)[0] in configured:
        bucket, object_path = raw_path.split("/", 1)
        candidates.insert(0, (bucket, object_path, bucket == settings.SUPABASE_PUBLIC_BUCKET))
    else:
        candidates.extend((bucket, raw_path, bucket == settings.SUPABASE_PUBLIC_BUCKET) for bucket in configured)

    seen = set()
    for candidate in candidates:
        bucket, object_path = candidate[:2]
        is_public = bool(candidate[2]) if len(candidate) > 2 else bucket == settings.SUPABASE_PUBLIC_BUCKET
        key = (bucket, object_path)
        if key in seen:
            continue
        seen.add(key)
        if is_public:
            return f"{settings.SUPABASE_URL}/storage/v1/object/public/{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
        signed = _signed_storage_url(bucket, object_path, expires)
        if signed:
            return signed
    return ""


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


def build_monthly_invoice_pdf(invoice):
    """Genera una factura/recibo PDF sencillo y portable para correo y buzón."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise ValidationError("Instala reportlab desde requirements.txt para generar facturas PDF.") from exc

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=invoice.invoice_number,
        author="MOVIX",
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph('<font color="#1f5fff"><b>MOVIX</b></font>', styles["Title"]),
        Paragraph("Tu carga, nuestro camino", styles["Normal"]),
        Spacer(1, 8 * mm),
        Paragraph(
            f"<b>Comprobante de mensualidad {html_escape(str(invoice.invoice_number))}</b>",
            styles["Heading2"],
        ),
        Spacer(1, 4 * mm),
    ]
    rows = [
        ["Transportista", str(invoice.customer_name)],
        ["Cédula", str(invoice.customer_identification or "No registrada")],
        ["Correo", str(invoice.customer_email or "No registrado")],
        ["Mensualidad", invoice.period.strftime("%m/%Y")],
        ["Valor", f"USD {invoice.amount:.2f}"],
        ["Banco / forma", f"{invoice.bank} · {invoice.payment_method}"],
        ["Fecha de emisión", timezone.localtime(invoice.issued_at or timezone.now()).strftime("%d/%m/%Y %H:%M")],
        ["Estado", "PAGADO"],
    ]
    table = Table(rows, colWidths=[45 * mm, 105 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf4ff")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#183153")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d7e1ee")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([
        table,
        Spacer(1, 9 * mm),
        Paragraph(
            "Este documento confirma el registro de la mensualidad del transportista en MOVIX. "
            "Conserva el número de factura para cualquier consulta.",
            styles["BodyText"],
        ),
    ])
    document.build(story)
    return output.getvalue()


def send_movix_email(
    recipient,
    subject,
    body,
    attachment_name=None,
    attachment_bytes=None,
    action_url=None,
    action_label=None,
):
    """Envía por Brevo HTTPS o SMTP y permite adjuntar una factura PDF."""
    if not recipient:
        return False, "El transportista no tiene correo registrado."
    action_html = ""
    if action_url:
        safe_url = html_escape(str(action_url), quote=True)
        safe_label = html_escape(str(action_label or "Abrir en MOVIX"))
        action_html = (
            '<p style="margin:28px 0">'
            f'<a href="{safe_url}" style="display:inline-block;background:#1f5eff;color:#fff;'
            'padding:13px 22px;border-radius:10px;text-decoration:none;font-weight:700">'
            f'{safe_label}</a></p>'
            f'<p style="font-size:12px;color:#71809a;word-break:break-all">{safe_url}</p>'
        )
    html = (
        '<div style="font-family:Arial,sans-serif;color:#183153;max-width:620px">'
        '<h2 style="color:#1f5fff">MOVIX</h2>'
        f'<h3>{html_escape(str(subject))}</h3>'
        f'<p style="line-height:1.6">{html_escape(str(body)).replace(chr(10), "<br>")}</p>'
        f'{action_html}'
        '<p style="color:#71809a">Tu carga, nuestro camino.</p></div>'
    )
    if settings.EMAIL_PROVIDER == "brevo":
        if not settings.BREVO_API_KEY:
            return False, "BREVO_API_KEY no está configurada en Render."
        if not settings.BREVO_SENDER_EMAIL:
            return False, "BREVO_SENDER_EMAIL no está configurado."
        payload = {
            "sender": {
                "name": settings.BREVO_SENDER_NAME or "MOVIX",
                "email": settings.BREVO_SENDER_EMAIL,
            },
            "to": [{"email": recipient}],
            "subject": str(subject),
            "textContent": str(body),
            "htmlContent": html,
        }
        if attachment_name and attachment_bytes:
            payload["attachment"] = [{
                "name": str(attachment_name),
                "content": base64.b64encode(attachment_bytes).decode("ascii"),
            }]
        try:
            response = requests.post(
                settings.BREVO_API_URL,
                headers={
                    "accept": "application/json",
                    "api-key": settings.BREVO_API_KEY,
                    "content-type": "application/json",
                },
                json=payload,
                timeout=(8, 25),
            )
            if response.status_code in {200, 201, 202}:
                return True, ""
            try:
                detail = response.json().get("message") or response.json().get("code")
            except ValueError:
                detail = response.text
            return False, f"Brevo respondió {response.status_code}: {str(detail or 'error desconocido')[:200]}"
        except requests.RequestException as exc:
            return False, f"No se pudo conectar con Brevo: {str(exc)[:210]}"

    email = EmailMultiAlternatives(
        subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient]
    )
    email.attach_alternative(html, "text/html")
    if attachment_name and attachment_bytes:
        email.attach(attachment_name, attachment_bytes, "application/pdf")
    try:
        email.send(fail_silently=False)
        return True, ""
    except Exception as exc:  # El mensaje del buzón no se pierde si SMTP falla.
        return False, str(exc)[:260]


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
    value = _clean_media_value(value)
    if value.startswith("storage://"):
        return True
    parsed = urlparse(value)
    if parsed.scheme == "https":
        allowed = {urlparse(settings.SUPABASE_URL).hostname, "res.cloudinary.com"}
        return parsed.hostname in allowed
    if parsed.scheme or parsed.netloc or value.startswith("//"):
        return False
    # Rutas relativas generadas por Storage son válidas; se rechaza traversal.
    parts = [part for part in value.split("?", 1)[0].replace("\\", "/").split("/") if part]
    return bool(parts) and ".." not in parts and ":" not in parts[0]
