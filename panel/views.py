import csv
import json
import uuid
from datetime import datetime

import requests
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import admin_required
from .forms import (
    AdminProfileForm,
    AdvertisementForm,
    NotificationForm,
    ProfileCreateForm,
    ProfileForm,
    SettingsForm,
)
from .models import (
    AdminProfile,
    Advertisement,
    AuditLog,
    DriverReview,
    Notification,
    NotificationCampaign,
    Profile,
    Ride,
    SystemSetting,
)
from .services import (
    active_tokens_for_users,
    audit,
    create_supabase_auth_user,
    delete_storage_object,
    delete_supabase_auth_user,
    is_safe_media_url,
    resolve_media_url,
    send_push_notifications,
    upload_to_supabase,
)


CLIENT_ROLES = ["cliente", "client", "usuario"]
DRIVER_ROLES = ["conductor", "driver", "transportista"]
DOCUMENT_FIELDS = {
    "identification": ("identification_photo_url", "Cédula de identidad"),
    "profile": ("profile_photo_url", "Foto de perfil"),
    "vehicle": ("vehicle_photo_url", "Foto del vehículo"),
    "license": ("license_photo_url", "Licencia de conducir"),
    "registration": ("registration_photo_url", "Matrícula vehicular"),
    "insurance": ("insurance_photo_url", "Seguro vehicular"),
}

REVERIFICATION_FIELDS = {
    "identification_number", "license_number", "vehicle_plate", "vehicle_year",
    "vehicle_type", "identification_file", "license_file", "registration_file", "insurance_file",
}


def _role_q(roles):
    query = Q()
    for role in roles:
        query |= Q(role__iexact=role)
    return query


def _verification_q(status):
    approved = Q(verification_status="approved") | Q(profile_verified=True) | Q(verified=True)
    rejected = Q(verification_status="rejected") & Q(profile_verified=False) & Q(verified=False)
    if status == "approved":
        return approved
    if status == "rejected":
        return rejected
    return ~approved & ~rejected


def _profile_queryset(kind):
    roles = DRIVER_ROLES if kind == "drivers" else CLIENT_ROLES
    return Profile.objects.filter(_role_q(roles))


def _kind_config(kind):
    if kind == "drivers":
        return {"singular": "Transportista", "plural": "Transportistas", "role": "transportista"}
    return {"singular": "Usuario", "plural": "Usuarios", "role": "cliente"}


def _upload_profile_files(profile, form, kind):
    mapping = {
        "identification_file": "identification_photo_url",
        "profile_file": "profile_photo_url",
        "vehicle_file": "vehicle_photo_url",
        "license_file": "license_photo_url",
        "registration_file": "registration_photo_url",
        "insurance_file": "insurance_photo_url",
    }
    replacements = []
    try:
        for form_field, model_field in mapping.items():
            uploaded = form.cleaned_data.get(form_field)
            if not uploaded:
                continue
            old_value = getattr(profile, model_field, "")
            value = upload_to_supabase(
                uploaded,
                folder=f"profiles/{profile.id}/{form_field}",
                public=form_field in {"profile_file", "vehicle_file"},
                images_only=form_field in {"profile_file", "vehicle_file"},
            )
            setattr(profile, model_field, value)
            if form_field == "profile_file":
                profile.avatar_url = value
            replacements.append((old_value, value))
    except ValidationError:
        _finish_file_replacements(replacements, saved=False)
        raise
    return replacements


def _finish_file_replacements(replacements, saved):
    """Evita perder el archivo anterior si la actualización de BD falla."""
    for old_value, new_value in replacements:
        delete_storage_object(old_value if saved else new_value)


def _monthly_counts(queryset, date_field="created_at"):
    now = timezone.localtime()
    labels = []
    months = []
    year, month = now.year, now.month
    for offset in range(5, -1, -1):
        current_month = month - offset
        current_year = year
        while current_month <= 0:
            current_month += 12
            current_year -= 1
        months.append((current_year, current_month))
        labels.append(datetime(current_year, current_month, 1).strftime("%b").title())
    rows = queryset.annotate(month=TruncMonth(date_field)).values("month").annotate(total=Count("id"))
    mapping = {(row["month"].year, row["month"].month): row["total"] for row in rows if row["month"]}
    return labels, [mapping.get(value, 0) for value in months]


@admin_required
def dashboard(request):
    completed_statuses = ["completada", "completado", "completed", "finalizada", "finalizado"]
    cached = cache.get("movix-dashboard-summary-v2")
    if cached is None:
        profile_stats = Profile.objects.aggregate(
            total=Count("id"),
            clients=Count("id", filter=_role_q(CLIENT_ROLES)),
            drivers=Count("id", filter=_role_q(DRIVER_ROLES)),
            verified_profiles=Count("id", filter=_verification_q("approved")),
            pending_profiles=Count("id", filter=_verification_q("pending")),
        )
        ride_stats = Ride.objects.aggregate(
            completed=Count("id", filter=Q(status__in=completed_statuses)),
            in_progress=Count("id", filter=Q(status__in=["aceptada", "en_camino", "en curso", "in_progress"])),
        )
        labels, client_series = _monthly_counts(_profile_queryset("users"))
        _, driver_series = _monthly_counts(_profile_queryset("drivers"))
        _, ride_series = _monthly_counts(Ride.objects.filter(status__in=completed_statuses))
        total_profiles = profile_stats["total"] or 0
        cached = {
            "client_count": profile_stats["clients"],
            "driver_count": profile_stats["drivers"],
            "completed_rides": ride_stats["completed"],
            "in_progress_rides": ride_stats["in_progress"],
            "verification_rate": round(((profile_stats["verified_profiles"] or 0) / total_profiles) * 100) if total_profiles else 0,
            "pending_verifications": profile_stats["pending_profiles"],
            "chart_data": {"labels": labels, "clients": client_series, "drivers": driver_series, "rides": ride_series},
        }
        cache.set("movix-dashboard-summary-v2", cached, 45)
    try:
        recent_activity = AuditLog.objects.all()[:6]
    except DatabaseError:
        recent_activity = []
    context = {
        **cached,
        "recent_drivers": _profile_queryset("drivers").only(
            "id", "first_name", "last_name", "email", "role", "profile_photo_url", "avatar_url",
            "vehicle_type", "vehicle_plate", "rating", "completed_trips", "load_capacity", "is_active", "is_available", "created_at",
        )[:4],
        "recent_activity": recent_activity,
    }
    return render(request, "panel/dashboard.html", context)


@admin_required
def profile_list(request, kind):
    config = _kind_config(kind)
    queryset = _profile_queryset(kind)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    if query:
        queryset = queryset.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(identification_number__icontains=query)
            | Q(cedula__icontains=query)
            | Q(vehicle_plate__icontains=query)
        )
    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "inactive":
        queryset = queryset.filter(is_active=False)
    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(request, "panel/profile_list.html", {"kind": kind, "config": config, "page": page, "query": query, "status": status})


@admin_required
def profile_detail(request, kind, profile_id):
    config = _kind_config(kind)
    profile = get_object_or_404(_profile_queryset(kind), pk=profile_id)
    reviews = DriverReview.objects.filter(driver=profile).select_related("client")[:8] if kind == "drivers" else DriverReview.objects.filter(client=profile).select_related("driver")[:8]
    ride_count = Ride.objects.filter(driver=profile).count() if kind == "drivers" else Ride.objects.filter(client=profile).count()
    return render(request, "panel/profile_detail.html", {"kind": kind, "config": config, "profile": profile, "reviews": reviews, "ride_count": ride_count})


@admin_required
def profile_create(request, kind):
    config = _kind_config(kind)
    role = config["role"]
    form = ProfileCreateForm(request.POST or None, request.FILES or None, role=role)
    if request.method == "POST" and form.is_valid():
        if Profile.objects.filter(email__iexact=form.cleaned_data["email"]).exists():
            form.add_error("email", "Ya existe un perfil con este correo electrónico.")
            return render(request, "panel/profile_form.html", {"kind": kind, "config": config, "form": form, "creating": True})
        created_auth_id = None
        replacements = []
        try:
            created_auth_id = create_supabase_auth_user(
                form.cleaned_data["email"],
                form.cleaned_data["password"],
                {"role": role, "first_name": form.cleaned_data["first_name"], "last_name": form.cleaned_data["last_name"]},
            )
            profile = Profile.objects.filter(pk=created_auth_id).first()
            already_exists = profile is not None
            if profile is None:
                profile = form.save(commit=False)
                profile.id = created_auth_id
            else:
                for field_name in ProfileForm.Meta.fields:
                    if field_name in form.cleaned_data:
                        setattr(profile, field_name, form.cleaned_data[field_name])
            profile.role = role
            profile.cedula = profile.identification_number
            profile.created_at = profile.created_at or timezone.now()
            profile.updated_at = timezone.now()
            profile.is_active = True
            profile.verification_status = "pending"
            replacements = _upload_profile_files(profile, form, kind)
            profile.save(force_insert=not already_exists)
            _finish_file_replacements(replacements, saved=True)
            cache.delete("movix-dashboard-summary-v2")
            audit(request, "create", "profile", f"Creó {config['singular'].lower()} {profile.full_name}", profile.id)
            messages.success(request, f"{config['singular']} creado correctamente.")
            return redirect("panel:profile_detail", kind=kind, profile_id=profile.id)
        except (ValidationError, DatabaseError) as exc:
            _finish_file_replacements(replacements, saved=False)
            if created_auth_id:
                try:
                    delete_supabase_auth_user(created_auth_id)
                except ValidationError:
                    pass
            form.add_error(None, exc)
    return render(request, "panel/profile_form.html", {"kind": kind, "config": config, "form": form, "creating": True})


@admin_required
def profile_edit(request, kind, profile_id):
    config = _kind_config(kind)
    profile = get_object_or_404(_profile_queryset(kind), pk=profile_id)
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile, role=config["role"])
    if request.method == "POST" and form.is_valid():
        replacements = []
        try:
            profile = form.save(commit=False)
            replacements = _upload_profile_files(profile, form, kind)
            profile.cedula = profile.identification_number
            profile.updated_at = timezone.now()
            if profile.effective_verification_status == "approved" and REVERIFICATION_FIELDS.intersection(form.changed_data):
                profile.profile_verified = False
                profile.verified = False
                profile.verification_status = "pending"
                profile.verified_at = None
            profile.save()
            _finish_file_replacements(replacements, saved=True)
            cache.delete("movix-dashboard-summary-v2")
            audit(request, "update", "profile", f"Actualizó {config['singular'].lower()} {profile.full_name}", profile.id)
            messages.success(request, "Los cambios y archivos fueron guardados correctamente.")
            return redirect("panel:profile_detail", kind=kind, profile_id=profile.id)
        except (ValidationError, DatabaseError) as exc:
            _finish_file_replacements(replacements, saved=False)
            form.add_error(None, exc)
    return render(request, "panel/profile_form.html", {"kind": kind, "config": config, "profile": profile, "form": form, "creating": False})


@admin_required
@require_POST
def profile_delete(request, kind, profile_id):
    config = _kind_config(kind)
    profile = get_object_or_404(_profile_queryset(kind), pk=profile_id)
    name = profile.full_name
    try:
        delete_supabase_auth_user(profile.id)
        if Profile.objects.filter(pk=profile.id).exists():
            profile.delete()
        cache.delete("movix-dashboard-summary-v2")
        audit(request, "delete", "profile", f"Eliminó {config['singular'].lower()} {name}", profile_id)
        messages.success(request, f"{config['singular']} eliminado de Supabase Auth y de la base de datos.")
    except (ValidationError, DatabaseError) as exc:
        messages.error(request, str(exc))
    return redirect("panel:profile_list", kind=kind)


@admin_required
@require_POST
def profile_toggle(request, kind, profile_id):
    profile = get_object_or_404(_profile_queryset(kind), pk=profile_id)
    profile.is_active = not profile.is_active
    profile.blocked_at = None if profile.is_active else timezone.now()
    profile.blocked_reason = None if profile.is_active else request.POST.get("reason", "Bloqueado desde el panel administrativo")
    profile.updated_at = timezone.now()
    profile.save(update_fields=["is_active", "blocked_at", "blocked_reason", "updated_at"])
    cache.delete("movix-dashboard-summary-v2")
    action = "unblock" if profile.is_active else "block"
    audit(request, action, "profile", f"{'Desbloqueó' if profile.is_active else 'Bloqueó'} a {profile.full_name}", profile.id)
    messages.success(request, f"{profile.full_name} ahora está {profile.status_label.lower()}.")
    return redirect(request.POST.get("next") or reverse("panel:profile_detail", kwargs={"kind": kind, "profile_id": profile.id}))


@admin_required
def profile_export(request, kind):
    config = _kind_config(kind)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="movix_{kind}_{timezone.localdate()}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["ID", "Nombres", "Correo", "Teléfono", "Cédula", "Estado", "Verificación", "Creado"])
    for profile in _profile_queryset(kind):
        writer.writerow([profile.id, profile.full_name, profile.email, profile.phone, profile.identity, profile.status_label, profile.verification_label, profile.created_at])
    audit(request, "export", "profile", f"Exportó el listado de {config['plural'].lower()}")
    return response


@admin_required
def verification_list(request):
    queryset = Profile.objects.all()
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    kind = request.GET.get("kind", "all")
    if query:
        queryset = queryset.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(identification_number__icontains=query) | Q(cedula__icontains=query))
    if status != "all":
        queryset = queryset.filter(_verification_q(status))
    if kind == "users":
        queryset = queryset.filter(_role_q(CLIENT_ROLES))
    elif kind == "drivers":
        queryset = queryset.filter(_role_q(DRIVER_ROLES))
    counts = Profile.objects.aggregate(
        pending=Count("id", filter=_verification_q("pending")),
        approved=Count("id", filter=_verification_q("approved")),
        rejected=Count("id", filter=_verification_q("rejected")),
    )
    return render(request, "panel/verification_list.html", {"profiles": queryset[:100], "counts": counts, "query": query, "status": status, "kind_filter": kind})


@admin_required
def verification_detail(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id)
    documents = []
    for key, (field_name, label) in DOCUMENT_FIELDS.items():
        if not profile.is_driver and key in {"vehicle", "license", "registration", "insurance"}:
            continue
        documents.append({"key": key, "label": label, "value": getattr(profile, field_name, "")})
    return render(request, "panel/verification_detail.html", {"profile": profile, "documents": documents, "kind": "drivers" if profile.is_driver else "users"})


@admin_required
@require_POST
def verification_update(request, profile_id, decision):
    profile = get_object_or_404(Profile, pk=profile_id)
    if decision not in {"approve", "reject"}:
        raise Http404
    if decision == "approve":
        required_documents = [("Cédula de identidad", profile.identification_photo_url)]
        if profile.is_driver:
            required_documents.extend([
                ("Licencia de conducir", profile.license_photo_url),
                ("Matrícula vehicular", profile.registration_photo_url),
                ("Seguro vehicular", profile.insurance_photo_url),
            ])
        missing = [label for label, value in required_documents if not value]
        if missing:
            messages.error(request, "No se puede aprobar. Faltan: " + ", ".join(missing) + ".")
            return redirect("panel:verification_detail", profile_id=profile.id)
        profile.verification_status = "approved"
        profile.profile_verified = True
        profile.verified = True
        profile.verified_at = timezone.now()
        profile.verification_rejection_reason = None
        profile.license_verified = bool(profile.license_photo_url) if profile.is_driver else profile.license_verified
        profile.registration_verified = bool(profile.registration_photo_url) if profile.is_driver else profile.registration_verified
        profile.insurance_verified = bool(profile.insurance_photo_url) if profile.is_driver else profile.insurance_verified
        message = "Verificación aprobada correctamente."
    else:
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "Escribe el motivo del rechazo.")
            return redirect("panel:verification_detail", profile_id=profile.id)
        profile.verification_status = "rejected"
        profile.profile_verified = False
        profile.verified = False
        profile.verified_at = None
        profile.verification_rejection_reason = reason
        profile.verification_notes = reason
        message = "Verificación rechazada y motivo registrado."
    profile.updated_at = timezone.now()
    profile.save()
    cache.delete("movix-dashboard-summary-v2")
    Notification.objects.create(
        id=uuid.uuid4(), user=profile, type="verification", title="Estado de tu verificación",
        message=message, is_read=False, created_at=timezone.now(),
    )
    audit(request, decision, "verification", f"{message} Perfil: {profile.full_name}", profile.id)
    messages.success(request, message)
    return redirect("panel:verification_list")


@admin_required
def document_access(request, profile_id, document_key, action="view"):
    profile = get_object_or_404(Profile, pk=profile_id)
    if document_key not in DOCUMENT_FIELDS:
        raise Http404
    field_name, label = DOCUMENT_FIELDS[document_key]
    value = getattr(profile, field_name, "")
    if not value or not is_safe_media_url(value):
        messages.error(request, "El archivo no existe o su origen no está permitido.")
        return redirect("panel:verification_detail", profile_id=profile.id)
    url = resolve_media_url(value, expires=300)
    if not url:
        messages.error(request, "No se pudo generar el enlace temporal del archivo.")
        return redirect("panel:verification_detail", profile_id=profile.id)
    if action == "view":
        return redirect(url)
    response = requests.get(url, stream=True, timeout=40)
    if response.status_code != 200:
        messages.error(request, "No se pudo descargar el archivo.")
        return redirect("panel:verification_detail", profile_id=profile.id)
    filename = url.split("?")[0].rstrip("/").split("/")[-1] or f"{label}.bin"
    download = StreamingHttpResponse(response.iter_content(chunk_size=8192), content_type=response.headers.get("Content-Type", "application/octet-stream"))
    download["Content-Disposition"] = f'attachment; filename="{filename}"'
    return download


@admin_required
def notifications_view(request):
    form = NotificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        audience = form.cleaned_data["audience"]
        if audience == "specific":
            recipients = Profile.objects.filter(pk=form.cleaned_data["recipient"].pk, is_active=True)
        elif audience == "clients":
            recipients = _profile_queryset("users").filter(is_active=True)
        elif audience == "drivers":
            recipients = _profile_queryset("drivers").filter(is_active=True)
        else:
            recipients = Profile.objects.filter(is_active=True)
        recipient_ids = list(recipients.values_list("id", flat=True))
        now = timezone.now()
        Notification.objects.bulk_create([
            Notification(id=uuid.uuid4(), user_id=user_id, type="admin", title=form.cleaned_data["title"], message=form.cleaned_data["message"], is_read=False, created_at=now)
            for user_id in recipient_ids
        ])
        tokens = active_tokens_for_users(recipient_ids)
        push_sent, push_error = send_push_notifications(tokens, form.cleaned_data["title"], form.cleaned_data["message"], {"type": "admin"})
        status = "delivered" if not push_error else "stored"
        NotificationCampaign.objects.create(
            id=uuid.uuid4(), audience=audience, recipient=form.cleaned_data.get("recipient"),
            title=form.cleaned_data["title"], message=form.cleaned_data["message"],
            total_recipients=len(recipient_ids), push_sent=push_sent, status=status,
            error_message=push_error or None, created_by=request.user.username, created_at=now,
        )
        audit(request, "send", "notification", f"Envió notificación a {len(recipient_ids)} destinatarios")
        messages.success(request, f"Notificación guardada para {len(recipient_ids)} destinatarios. Push enviados: {push_sent}.")
        return redirect("panel:notifications")
    campaigns = NotificationCampaign.objects.all()[:10]
    return render(request, "panel/notifications.html", {"form": form, "campaigns": campaigns})


@admin_required
def advertisements_view(request):
    form = AdvertisementForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        uploaded_value = ""
        try:
            advertisement = form.save(commit=False)
            advertisement.id = uuid.uuid4()
            uploaded_value = upload_to_supabase(form.cleaned_data["image"], "advertisements", public=True, images_only=True)
            advertisement.image_url = uploaded_value
            advertisement.created_by = request.user.username
            advertisement.created_at = timezone.now()
            advertisement.updated_at = timezone.now()
            advertisement.save(force_insert=True)
            audit(request, "create", "advertisement", f"Publicó banner {advertisement.title}", advertisement.id)
            messages.success(request, "Banner subido y publicado correctamente.")
            return redirect("panel:advertisements")
        except (ValidationError, DatabaseError) as exc:
            if uploaded_value:
                delete_storage_object(uploaded_value)
            form.add_error(None, exc)
    advertisements = Advertisement.objects.all()
    return render(request, "panel/advertisements.html", {"form": form, "advertisements": advertisements})


@admin_required
@require_POST
def advertisement_toggle(request, advertisement_id):
    advertisement = get_object_or_404(Advertisement, pk=advertisement_id)
    advertisement.is_active = not advertisement.is_active
    advertisement.updated_at = timezone.now()
    advertisement.save(update_fields=["is_active", "updated_at"])
    audit(request, "toggle", "advertisement", f"Cambió banner {advertisement.title} a {'activo' if advertisement.is_active else 'inactivo'}", advertisement.id)
    return redirect("panel:advertisements")


@admin_required
@require_POST
def advertisement_delete(request, advertisement_id):
    advertisement = get_object_or_404(Advertisement, pk=advertisement_id)
    delete_storage_object(advertisement.image_url)
    title = advertisement.title
    advertisement.delete()
    audit(request, "delete", "advertisement", f"Eliminó banner {title}", advertisement_id)
    messages.success(request, "Banner eliminado.")
    return redirect("panel:advertisements")


@admin_required
def admin_profile_view(request):
    admin_profile, _ = AdminProfile.objects.get_or_create(user=request.user)
    profile_form = AdminProfileForm(request.POST or None, request.FILES or None, user=request.user, prefix="profile")
    password_form = PasswordChangeForm(request.user, request.POST or None, prefix="password")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profile" and profile_form.is_valid():
            try:
                request.user.first_name = profile_form.cleaned_data["first_name"]
                request.user.last_name = profile_form.cleaned_data["last_name"]
                request.user.email = profile_form.cleaned_data["email"]
                request.user.save(update_fields=["first_name", "last_name", "email"])
                admin_profile.phone = profile_form.cleaned_data["phone"]
                admin_profile.city = profile_form.cleaned_data["city"]
                if profile_form.cleaned_data.get("avatar"):
                    admin_profile.avatar_url = upload_to_supabase(profile_form.cleaned_data["avatar"], f"admins/{request.user.id}", public=True, images_only=True)
                if profile_form.cleaned_data.get("cover"):
                    admin_profile.cover_url = upload_to_supabase(profile_form.cleaned_data["cover"], f"admins/{request.user.id}", public=True, images_only=True)
                admin_profile.save()
                audit(request, "update", "admin_profile", "Actualizó su perfil administrativo", request.user.id)
                messages.success(request, "Perfil actualizado.")
                return redirect("panel:admin_profile")
            except ValidationError as exc:
                profile_form.add_error(None, exc)
        if action == "password" and password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            audit(request, "update", "password", "Actualizó su contraseña")
            messages.success(request, "Contraseña actualizada.")
            return redirect("panel:admin_profile")
    stats = {
        "users": _profile_queryset("users").count(),
        "drivers": _profile_queryset("drivers").count(),
        "pending": Profile.objects.filter(_verification_q("pending")).count(),
    }
    return render(request, "panel/admin_profile.html", {"admin_profile": admin_profile, "profile_form": profile_form, "password_form": password_form, "stats": stats})


@admin_required
@require_POST
def admin_account_delete(request):
    if not request.user.check_password(request.POST.get("password", "")):
        messages.error(request, "La contraseña es incorrecta.")
        return redirect("panel:admin_profile")
    if User.objects.filter(is_staff=True, is_active=True).exclude(pk=request.user.pk).count() == 0:
        messages.error(request, "No puedes eliminar la única cuenta administrativa activa.")
        return redirect("panel:admin_profile")
    username = request.user.username
    request.user.delete()
    messages.success(request, f"La cuenta {username} fue eliminada.")
    return redirect("login")


@admin_required
def settings_view(request):
    defaults = {
        "app_name": "MOVIX",
        "support_email": "",
        "max_upload_mb": 10,
        "notifications_enabled": True,
        "maintenance_mode": False,
        "dark_mode": False,
    }
    setting = SystemSetting.objects.filter(pk="general").first()
    if setting and isinstance(setting.value, dict):
        defaults.update(setting.value)
    form = SettingsForm(request.POST or None, initial=defaults)
    if request.method == "POST" and form.is_valid():
        value = form.cleaned_data.copy()
        SystemSetting.objects.update_or_create(
            key="general",
            defaults={"value": value, "updated_by": request.user.username, "updated_at": timezone.now()},
        )
        audit(request, "update", "settings", "Actualizó la configuración general")
        messages.success(request, "Configuración guardada.")
        response = redirect("panel:settings")
        response.set_cookie("movix_dark_mode", "1" if value["dark_mode"] else "0", max_age=31536000, samesite="Lax")
        return response
    return render(request, "panel/settings.html", {"form": form})


@admin_required
def global_search(request):
    query = request.GET.get("q", "").strip().lower()
    modules = [
        ("Inicio", "panel:dashboard"), ("Usuarios", "panel:profile_list", "users"),
        ("Transportistas", "panel:profile_list", "drivers"), ("Notificaciones", "panel:notifications"),
        ("Publicidad", "panel:advertisements"), ("Verificar documentos", "panel:verification_list"),
        ("Perfil", "panel:admin_profile"), ("Configuración", "panel:settings"),
    ]
    results = [item for item in modules if len(query) >= 2 and query in item[0].lower()]
    return render(request, "panel/search.html", {"query": query, "module_results": results})
