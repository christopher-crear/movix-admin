import csv
import hashlib
import json
import mimetypes
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as django_login, logout as django_logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core import signing
from django.core.files.base import ContentFile
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError, transaction
from django.db.models import Avg, Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from .decorators import admin_required, driver_portal_required
from .forms import (
    AdminProfileForm,
    AdvertisementForm,
    ContactResponseForm,
    DriverBlockForm,
    DriverInboxMessageForm,
    DriverMonthlyPaymentForm,
    DriverSelfProfileForm,
    NotificationForm,
    PaymentBankAccountForm,
    PublicContactForm,
    PublicDriverRegistrationForm,
    PasswordRecoveryRequestForm,
    PasswordResetConfirmForm,
    ProfileCreateForm,
    ProfileForm,
    SettingsForm,
    SupabasePasswordChangeForm,
)
from .models import (
    AdminProfile,
    Advertisement,
    AuditLog,
    ContactRequest,
    DriverInboxMessage,
    DriverInvoice,
    DriverMonthlyPayment,
    DriverReview,
    Notification,
    NotificationCampaign,
    PaymentBankAccount,
    Profile,
    Ride,
    SystemSetting,
)
from .services import (
    active_tokens_for_users,
    audit,
    build_monthly_invoice_pdf,
    create_supabase_auth_user,
    delete_storage_object,
    delete_supabase_auth_user,
    is_safe_media_url,
    resolve_media_url,
    send_movix_email,
    send_push_notifications,
    supabase_password_sign_in,
    supabase_admin_update_password,
    supabase_update_password,
    supabase_user_from_token,
    upload_to_supabase,
)


CLIENT_ROLES = ["cliente", "client", "usuario"]
DRIVER_ROLES = ["conductor", "driver", "transportista"]
COMPLETED_RIDE_STATUSES = ["completada", "completado", "completed", "finalizada", "finalizado"]
CANCELLED_RIDE_STATUSES = ["cancelada", "cancelado", "cancelled", "canceled"]
DOCUMENT_FIELDS = {
    "identification": ("identification_photo_url", "Cédula de identidad"),
    "profile": ("profile_photo_url", "Foto de perfil"),
    "vehicle": ("vehicle_photo_url", "Foto del vehículo"),
    "license": ("license_photo_url", "Licencia de conducir"),
    "registration": ("registration_photo_url", "Matrícula vehicular"),
    "insurance": ("insurance_photo_url", "Seguro vehicular"),
}
PUBLIC_DOCUMENT_KEYS = {"profile", "vehicle"}

REVERIFICATION_FIELDS = {
    "identification_number", "license_number", "vehicle_plate", "vehicle_year",
    "vehicle_type", "identification_file", "license_file", "registration_file", "insurance_file",
}


def _profile_document_items(profile, keys=None):
    """Construye una lista uniforme para todas las previsualizaciones."""
    allowed_keys = set(keys) if keys else None
    documents = []
    for key, (field_name, label) in DOCUMENT_FIELDS.items():
        if allowed_keys is not None and key not in allowed_keys:
            continue
        if not profile.is_driver and key in {"vehicle", "license", "registration", "insurance"}:
            continue
        value = getattr(profile, field_name, "")
        if key == "profile" and not value:
            value = profile.avatar_url
        if not value:
            status, status_label = "missing", "Sin archivo"
        elif key == "license":
            status, status_label = ("approved", "Verificado") if profile.license_verified else ("pending", "Pendiente")
        elif key == "registration":
            status, status_label = ("approved", "Verificado") if profile.registration_verified else ("pending", "Pendiente")
        elif key == "insurance":
            status, status_label = ("approved", "Verificado") if profile.insurance_verified else ("pending", "Pendiente")
        elif key == "identification":
            status = profile.effective_verification_status
            status_label = profile.verification_label
        else:
            status, status_label = "uploaded", "Cargado"
        if value and profile.effective_verification_status == "rejected" and key not in {"profile", "vehicle"}:
            status, status_label = "rejected", "Rechazado"
        documents.append({"key": key, "label": label, "value": value, "status": status, "status_label": status_label})
    return documents


def landing(request):
    """Página pública de presentación de MOVIX y recepción de solicitudes."""
    form = PublicContactForm(request.POST or None)
    if request.method == "POST":
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip_address = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
        rate_key = f"movix-public-contact:{ip_address or 'unknown'}"
        attempts = int(cache.get(rate_key, 0))
        if attempts >= 5:
            form.add_error(None, "Has enviado varias solicitudes. Espera unos minutos antes de intentarlo otra vez.")
        elif form.is_valid():
            contact = form.save(commit=False)
            contact.ip_address = ip_address or None
            contact.user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
            contact.save()
            cache.set(rate_key, attempts + 1, 600)
            cache.delete("movix-new-contact-count")
            return redirect(f"{reverse('panel:landing')}?enviado=1#contacto")
    return render(
        request,
        "landing.html",
        {
            "contact_form": form,
            "support_email": settings.MOVIX_SUPPORT_EMAIL,
            "whatsapp_number": settings.MOVIX_WHATSAPP_NUMBER,
            "whatsapp_display": settings.MOVIX_WHATSAPP_DISPLAY,
            "facebook_url": settings.MOVIX_FACEBOOK_URL,
        },
    )


def demo_app(request):
    """Simulación pública y aislada del flujo móvil de MOVIX."""
    return render(request, "demo.html")


def terms_and_conditions(request):
    """Condiciones informativas de demostración para el registro público."""
    return render(request, "registration/terms.html")


def driver_registration(request):
    """Alta pública de transportistas en Supabase Auth, Profile y Storage."""
    if request.user.is_authenticated or request.session.get("portal_profile_id"):
        return redirect("login")
    form = PublicDriverRegistrationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if Profile.objects.filter(email__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
            form.add_error("email", "Ya existe una cuenta MOVIX con este correo.")
        else:
            created_auth_id = None
            replacements = []
            try:
                created_auth_id = create_supabase_auth_user(
                    email,
                    form.cleaned_data["password"],
                    {
                        "role": "transportista",
                        "first_name": form.cleaned_data["first_name"],
                        "last_name": form.cleaned_data["last_name"],
                        "terms_accepted": True,
                        "terms_version": "demo-2026-08",
                    },
                )
                with transaction.atomic():
                    profile = Profile.objects.filter(pk=created_auth_id).first()
                    already_exists = profile is not None
                    if profile is None:
                        profile = form.save(commit=False)
                        profile.id = created_auth_id
                    else:
                        for field_name in ProfileForm.Meta.fields:
                            if field_name in form.cleaned_data:
                                setattr(profile, field_name, form.cleaned_data[field_name])
                    profile.role = "transportista"
                    profile.cedula = profile.identification_number
                    profile.created_at = profile.created_at or timezone.now()
                    profile.updated_at = timezone.now()
                    profile.is_active = True
                    profile.is_available = False
                    profile.verified = False
                    profile.profile_verified = False
                    profile.verification_status = "pending"
                    replacements = _upload_profile_files(profile, form, "drivers")
                    profile.save(force_insert=not already_exists)
                _finish_file_replacements(replacements, saved=True)
                send_movix_email(
                    email,
                    "Registro recibido en MOVIX",
                    "Tu cuenta de transportista fue creada. Revisaremos tus datos y documentos. "
                    "Ya puedes ingresar al portal para consultar el estado de la verificación.",
                    action_url=request.build_absolute_uri(reverse("login")),
                    action_label="Ingresar a MOVIX",
                )
                messages.success(request, "Registro completado. Tus documentos quedaron pendientes de revisión.")
                return redirect("login")
            except (ValidationError, DatabaseError, requests.RequestException) as exc:
                _finish_file_replacements(replacements, saved=False)
                if created_auth_id:
                    try:
                        delete_supabase_auth_user(created_auth_id)
                    except (ValidationError, requests.RequestException):
                        pass
                form.add_error(None, exc)
    return render(request, "registration/driver_register.html", {"form": form})


def password_recovery(request):
    """Solicita un enlace firmado sin revelar si el correo está registrado."""
    form = PasswordRecoveryRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        profile = Profile.objects.filter(email__iexact=email).first()
        staff_user = User.objects.filter(email__iexact=email, is_active=True, is_staff=True).first()
        payload = None
        if profile:
            payload = {"kind": "supabase", "id": str(profile.id), "email": email, "nonce": uuid.uuid4().hex}
        elif staff_user:
            payload = {"kind": "django", "id": staff_user.pk, "email": email, "nonce": uuid.uuid4().hex}
        if payload:
            token = signing.dumps(payload, salt="movix-password-reset", compress=True)
            reset_url = request.build_absolute_uri(reverse("password_reset_confirm", kwargs={"token": token}))
            send_movix_email(
                email,
                "Recupera tu contraseña de MOVIX",
                "Recibimos una solicitud para cambiar tu contraseña. El enlace será válido por 30 minutos. "
                "Si no hiciste esta solicitud, ignora este mensaje.",
                action_url=reset_url,
                action_label="Crear nueva contraseña",
            )
        return render(request, "registration/password_recovery_sent.html", {"email": email})
    return render(request, "registration/password_recovery.html", {"form": form})


def password_reset_confirm(request, token):
    """Valida el enlace firmado y cambia la clave en Django o Supabase Auth."""
    invalid = False
    payload = None
    token_key = f"movix-reset-used:{hashlib.sha256(token.encode()).hexdigest()}"
    try:
        payload = signing.loads(token, salt="movix-password-reset", max_age=30 * 60)
        if cache.get(token_key):
            invalid = True
    except (signing.BadSignature, signing.SignatureExpired):
        invalid = True

    form = PasswordResetConfirmForm(request.POST or None)
    if request.method == "POST" and not invalid and form.is_valid():
        try:
            if payload.get("kind") == "django":
                user = User.objects.get(pk=payload["id"], is_active=True, is_staff=True)
                user.set_password(form.cleaned_data["new_password"])
                user.save(update_fields=["password"])
            else:
                profile = Profile.objects.get(pk=payload["id"], email__iexact=payload["email"])
                supabase_admin_update_password(profile.id, form.cleaned_data["new_password"])
            cache.set(token_key, True, 60 * 60)
            return render(request, "registration/password_reset_done.html")
        except (User.DoesNotExist, Profile.DoesNotExist, ValidationError, DatabaseError) as exc:
            form.add_error(None, str(exc))
    return render(
        request,
        "registration/password_reset_confirm.html",
        {"form": form, "invalid": invalid},
    )


def _portal_profile_from_auth(request, auth_user, auth_payload):
    """Crea una sesión web usando la identidad ya verificada por Supabase."""
    user_id = auth_user.get("id")
    email = (auth_user.get("email") or "").strip()
    if not user_id:
        raise ValidationError("Supabase no devolvió el identificador de la cuenta.")
    profile = Profile.objects.filter(pk=user_id).first()
    if not profile:
        raise ValidationError("La cuenta existe en Supabase Auth, pero todavía no tiene un perfil en MOVIX.")
    if not profile.is_active:
        raise ValidationError("Tu cuenta está bloqueada. Comunícate con soporte MOVIX.")

    # La coincidencia de correo nunca concede permisos administrativos. El rol
    # de la identidad de Supabase es la fuente de verdad para este flujo.
    profile_role = (profile.role or "").strip().lower()
    if profile_role in {"admin", "administrator", "administrador"}:
        staff_user = User.objects.filter(
            email__iexact=email,
            is_staff=True,
            is_active=True,
        ).first() if email else None
        if not staff_user:
            raise ValidationError(
                "El perfil indica un rol administrativo, pero no existe una cuenta administrativa habilitada en Django."
            )
        django_login(request, staff_user, backend="django.contrib.auth.backends.ModelBackend")
        return reverse("panel:dashboard")

    if not profile.is_driver:
        raise ValidationError("Este portal web está disponible para transportistas. Los clientes continúan usando la app MOVIX.")

    request.session.cycle_key()
    request.session["portal_profile_id"] = str(profile.id)
    request.session["portal_role"] = "transportista"
    request.session["portal_access_token"] = auth_payload.get("access_token", "")
    request.session["portal_refresh_token"] = auth_payload.get("refresh_token", "")
    request.session.set_expiry(60 * 60 * 12)
    return reverse("panel:driver_dashboard")


def access_login(request):
    """Login único: administradores Django y cuentas reales de Supabase."""
    # En una visita normal evitamos mostrar el formulario a quien ya inició
    # sesión. En un POST, en cambio, siempre validamos las credenciales
    # recibidas: una sesión anterior nunca debe hacer que se ignore la clave.
    if request.method != "POST":
        if request.user.is_authenticated and request.user.is_staff:
            return redirect("panel:dashboard")
        if request.session.get("portal_profile_id"):
            return redirect("panel:driver_dashboard")

    google_callback = request.build_absolute_uri(reverse("panel:auth_callback"))
    google_url = ""
    if settings.SUPABASE_URL:
        google_url = f"{settings.SUPABASE_URL}/auth/v1/authorize?{urlencode({'provider': 'google', 'redirect_to': google_callback})}"

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not identifier or not password:
            messages.error(request, "Escribe el usuario o correo y la contraseña.")
            return render(request, "registration/login.html", {"google_url": google_url})

        # El nombre de usuario (sin @) pertenece exclusivamente al acceso
        # administrativo de Django. Aquí Django comprueba usuario y clave; no
        # se consulta Supabase ni se intenta adivinar el rol por el correo.
        if "@" not in identifier:
            django_user = authenticate(request, username=identifier, password=password)
            if django_user and django_user.is_active and django_user.is_staff:
                request.session.pop("portal_profile_id", None)
                request.session.pop("portal_role", None)
                request.session.pop("portal_access_token", None)
                request.session.pop("portal_refresh_token", None)
                django_login(request, django_user)
                return redirect(request.POST.get("next") or "panel:dashboard")
            messages.error(request, "Usuario o contraseña incorrectos.")
            return render(request, "registration/login.html", {"google_url": google_url})

        # Si el correo pertenece a un transportista activo, se valida primero
        # contra Supabase. Así un correo repetido en auth_user de Django no
        # convierte accidentalmente al transportista en administrador.
        prefer_driver_role = False
        if "@" in identifier:
            driver_role_filter = Q()
            for role in DRIVER_ROLES:
                driver_role_filter |= Q(role__iexact=role)
            prefer_driver_role = Profile.objects.filter(
                email__iexact=identifier,
                is_active=True,
            ).filter(driver_role_filter).exists()

        if prefer_driver_role:
            try:
                payload = supabase_password_sign_in(identifier, password)
                destination = _portal_profile_from_auth(request, payload.get("user") or {}, payload)
                return redirect(destination)
            except (ValidationError, DatabaseError):
                messages.error(request, "Correo o contraseña incorrectos.")
            return render(request, "registration/login.html", {"google_url": google_url})

        # Mantiene compatible el acceso creado con `createsuperuser`.
        django_username = identifier
        if "@" in identifier:
            staff_match = User.objects.filter(email__iexact=identifier, is_staff=True).first()
            if staff_match:
                django_username = staff_match.username
        django_user = authenticate(request, username=django_username, password=password)
        if django_user and django_user.is_staff:
            django_login(request, django_user)
            return redirect(request.POST.get("next") or "panel:dashboard")

        # Para usuarios de la app, el identificador debe ser el correo real.
        try:
            payload = supabase_password_sign_in(identifier, password)
            destination = _portal_profile_from_auth(request, payload.get("user") or {}, payload)
            return redirect(destination)
        except (ValidationError, DatabaseError):
            messages.error(request, "Correo o contraseña incorrectos.")

    return render(request, "registration/login.html", {"google_url": google_url})


def auth_callback(request):
    """Página puente: el token de Google llega en el fragmento del navegador."""
    return render(request, "registration/auth_callback.html")


@require_POST
def auth_session(request):
    access_token = request.POST.get("access_token", "").strip()
    refresh_token = request.POST.get("refresh_token", "").strip()
    if not access_token:
        messages.error(request, "Google no devolvió una sesión válida.")
        return redirect("login")
    try:
        auth_user = supabase_user_from_token(access_token)
        destination = _portal_profile_from_auth(
            request,
            auth_user,
            {"access_token": access_token, "refresh_token": refresh_token},
        )
        return redirect(destination)
    except (ValidationError, DatabaseError) as exc:
        messages.error(request, str(exc))
        return redirect("login")


@require_POST
def access_logout(request):
    request.session.pop("portal_profile_id", None)
    request.session.pop("portal_role", None)
    request.session.pop("portal_access_token", None)
    request.session.pop("portal_refresh_token", None)
    if request.user.is_authenticated:
        django_logout(request)
    return redirect("login")


def _current_driver(request):
    profile_id = request.session.get("portal_profile_id")
    profile = Profile.objects.filter(pk=profile_id).first() if profile_id else None
    if not profile or not profile.is_driver or not profile.is_active:
        request.session.pop("portal_profile_id", None)
        raise PermissionDenied("La sesión no corresponde a un transportista activo.")
    return profile


def _ride_earnings(queryset):
    amount = queryset.aggregate(
        total=Sum(
            Coalesce("driver_price", "price"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )["total"]
    return amount or Decimal("0")


def _driver_common_context(driver):
    avatar_value = driver.profile_photo_url or driver.avatar_url
    return {
        "driver": driver,
        "driver_avatar_url": resolve_media_url(
            avatar_value,
            expires=900,
            preferred_buckets=(settings.SUPABASE_PUBLIC_BUCKET, settings.SUPABASE_PRIVATE_BUCKET),
        ) if avatar_value else "",
    }


@driver_portal_required
def driver_dashboard(request):
    driver = _current_driver(request)
    rides = Ride.objects.filter(driver=driver)
    completed = rides.filter(status__in=COMPLETED_RIDE_STATUSES)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    previous_week_start = week_start - timedelta(days=7)
    weekly_rides = completed.filter(completed_at__date__gte=week_start)
    previous_week_rides = completed.filter(
        completed_at__date__gte=previous_week_start,
        completed_at__date__lt=week_start,
    )
    weekly_earnings = _ride_earnings(weekly_rides)
    previous_earnings = _ride_earnings(previous_week_rides)
    if previous_earnings:
        weekly_change = round(((weekly_earnings - previous_earnings) / previous_earnings) * 100)
    else:
        weekly_change = 100 if weekly_earnings else 0

    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    daily_rows = completed.filter(completed_at__date__gte=days[0]).annotate(day=TruncDate("completed_at")).values("day").annotate(
        total=Sum(Coalesce("driver_price", "price"), output_field=DecimalField(max_digits=14, decimal_places=2))
    )
    daily_map = {row["day"]: row["total"] or Decimal("0") for row in daily_rows}
    max_daily = max([daily_map.get(day, Decimal("0")) for day in days] or [Decimal("0")])
    day_names = ["L", "M", "M", "J", "V", "S", "D"]
    daily_bars = []
    for day in days:
        value = daily_map.get(day, Decimal("0"))
        height = 18 if not max_daily else max(18, round(float(value / max_daily) * 100))
        daily_bars.append({"label": day_names[day.weekday()], "value": value, "height": height, "is_today": day == today})

    review_stats = DriverReview.objects.filter(driver=driver).aggregate(average=Avg("rating"), total=Count("id"))
    distance = completed.aggregate(total=Sum("distance_km"))["total"] or Decimal("0")
    context = {
        **_driver_common_context(driver),
        "weekly_earnings": weekly_earnings,
        "weekly_change": weekly_change,
        "daily_bars": daily_bars,
        "today_trips": completed.filter(completed_at__date=today).count(),
        "today_earnings": _ride_earnings(completed.filter(completed_at__date=today)),
        "distance": distance,
        "average_rating": review_stats["average"] or driver.rating or 0,
        "review_count": review_stats["total"],
        "accepted_count": rides.count(),
        "completed_count": completed.count(),
        "recent_rides": rides.select_related("client").order_by("-created_at")[:5],
    }
    return render(request, "driver/dashboard.html", context)


@driver_portal_required
def driver_rides(request):
    driver = _current_driver(request)
    queryset = Ride.objects.filter(driver=driver).select_related("client").order_by("-created_at")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    if query:
        queryset = queryset.filter(Q(origin_address__icontains=query) | Q(destination_address__icontains=query) | Q(cargo_description__icontains=query))
    if status == "completed":
        queryset = queryset.filter(status__in=COMPLETED_RIDE_STATUSES)
    elif status == "cancelled":
        queryset = queryset.filter(status__in=CANCELLED_RIDE_STATUSES)
    elif status == "active":
        queryset = queryset.exclude(status__in=COMPLETED_RIDE_STATUSES + CANCELLED_RIDE_STATUSES)
    page = Paginator(queryset, 10).get_page(request.GET.get("page"))
    context = {**_driver_common_context(driver), "page": page, "query": query, "status": status}
    return render(request, "driver/rides.html", context)


@driver_portal_required
def driver_ride_detail(request, ride_id):
    driver = _current_driver(request)
    ride = get_object_or_404(Ride.objects.select_related("client"), pk=ride_id, driver=driver)
    review = DriverReview.objects.filter(ride=ride, driver=driver).select_related("client").first()
    client_photo = ride.client.profile_photo_url or ride.client.avatar_url
    context = {
        **_driver_common_context(driver),
        "ride": ride,
        "review": review,
        "client_avatar_url": resolve_media_url(
            client_photo,
            expires=900,
            preferred_buckets=(settings.SUPABASE_PUBLIC_BUCKET, settings.SUPABASE_PRIVATE_BUCKET),
        ) if client_photo else "",
    }
    return render(request, "driver/ride_detail.html", context)


@driver_portal_required
def driver_reviews(request):
    driver = _current_driver(request)
    queryset = DriverReview.objects.filter(driver=driver).select_related("client", "ride")
    page = Paginator(queryset, 10).get_page(request.GET.get("page"))
    stats = queryset.aggregate(average=Avg("rating"), total=Count("id"))
    distribution_rows = queryset.values("rating").annotate(total=Count("id"))
    distribution_map = {row["rating"]: row["total"] for row in distribution_rows}
    distribution = [{"stars": value, "total": distribution_map.get(value, 0)} for value in range(5, 0, -1)]
    context = {
        **_driver_common_context(driver),
        "page": page,
        "average_rating": stats["average"] or driver.rating or 0,
        "review_total": stats["total"],
        "distribution": distribution,
    }
    return render(request, "driver/reviews.html", context)


@driver_portal_required
def driver_profile(request):
    driver = _current_driver(request)
    action = request.POST.get("action", "")
    editing = request.GET.get("editar") == "1" or action == "profile"
    profile_form = DriverSelfProfileForm(request.POST or None, request.FILES or None, instance=driver)
    password_form = SupabasePasswordChangeForm(
        request.POST if action == "password" else None
    )

    if request.method == "POST" and action == "profile" and profile_form.is_valid():
        replacements = []
        try:
            changed_files = {
                name
                for name in ["identification_file", "license_file", "registration_file", "insurance_file"]
                if profile_form.cleaned_data.get(name)
            }
            driver = profile_form.save(commit=False)
            replacements = _upload_profile_files(driver, profile_form, "drivers")
            driver.updated_at = timezone.now()
            if changed_files:
                driver.profile_verified = False
                driver.verified = False
                driver.verification_status = "pending"
                driver.verified_at = None
            driver.save()
            _finish_file_replacements(replacements, saved=True)
            messages.success(request, "Tu perfil fue actualizado correctamente.")
            return redirect("panel:driver_profile")
        except (ValidationError, DatabaseError) as exc:
            _finish_file_replacements(replacements, saved=False)
            profile_form.add_error(None, exc)

    if request.method == "POST" and action == "password" and password_form.is_valid():
        token = request.session.get("portal_access_token", "")
        if not token:
            password_form.add_error(None, "Vuelve a iniciar sesión para cambiar tu contraseña.")
        else:
            try:
                supabase_update_password(token, password_form.cleaned_data["new_password"])
                messages.success(request, "Tu contraseña de Supabase fue actualizada.")
                return redirect("panel:driver_profile")
            except ValidationError as exc:
                password_form.add_error(None, exc)

    context = {
        **_driver_common_context(driver),
        "editing": editing,
        "profile_form": profile_form,
        "password_form": password_form,
        "ride_count": Ride.objects.filter(driver=driver).count(),
        "review_stats": DriverReview.objects.filter(driver=driver).aggregate(average=Avg("rating"), total=Count("id")),
        "documents": _profile_document_items(driver),
    }
    return render(request, "driver/profile.html", context)


@driver_portal_required
def driver_payments(request):
    driver = _current_driver(request)
    current_period = timezone.localdate().replace(day=1)
    bank_accounts = list(PaymentBankAccount.objects.filter(is_active=True))
    form = DriverMonthlyPaymentForm(
        request.POST or None,
        request.FILES or None,
        initial={"period": current_period},
        bank_accounts=bank_accounts,
    )
    if request.method == "POST" and form.is_valid():
        period = form.cleaned_data["period"]
        if DriverMonthlyPayment.objects.filter(driver=driver, period=period).exists():
            form.add_error("period", "Ya registraste un pago para este mes. El administrador debe revisarlo.")
        else:
            receipt_value = ""
            try:
                receipt = form.cleaned_data.get("receipt")
                if receipt:
                    receipt_value = upload_to_supabase(
                        receipt,
                        folder=f"monthly-payments/{driver.id}/{period:%Y-%m}",
                        public=False,
                        images_only=False,
                    )
                payment = form.save(commit=False)
                payment.id = uuid.uuid4()
                payment.driver = driver
                payment.receipt_url = receipt_value or None
                payment.status = DriverMonthlyPayment.STATUS_PENDING
                payment.created_at = timezone.now()
                payment.updated_at = payment.created_at
                payment.save(force_insert=True)
                if payment.payment_method == "cash":
                    messages.success(request, "Pago físico registrado. El administrador confirmará la recepción del dinero.")
                else:
                    messages.success(request, "Comprobante enviado. El administrador revisará tu mensualidad.")
                return redirect("panel:driver_payments")
            except (ValidationError, DatabaseError) as exc:
                if receipt_value:
                    delete_storage_object(receipt_value)
                form.add_error(None, exc)

    payment_status = request.GET.get("status", "all")
    history = DriverMonthlyPayment.objects.filter(driver=driver).select_related("invoice")
    if payment_status in {"pending", "approved", "rejected"}:
        history = history.filter(status=payment_status)
    bank_cards = []
    for account in bank_accounts:
        logo_url = ""
        if account.logo_url:
            logo_url = reverse("panel:payment_bank_asset", kwargs={"bank_id": account.id, "asset": "logo", "action": "view"})
        bank_cards.append({"account": account, "logo_url": logo_url})
    page = Paginator(history, 8).get_page(request.GET.get("page"))
    return render(request, "driver/payments.html", {
        **_driver_common_context(driver),
        "form": form,
        "page": page,
        "payment_status": payment_status,
        "current_payment": DriverMonthlyPayment.objects.filter(driver=driver, period=current_period).first(),
        "bank_cards": bank_cards,
    })


@driver_portal_required
def driver_invoices(request):
    """Listado privado de las facturas emitidas al transportista autenticado."""
    driver = _current_driver(request)
    query = request.GET.get("q", "").strip()
    year = request.GET.get("year", "all").strip()
    base_queryset = DriverInvoice.objects.filter(driver=driver).select_related("payment")
    queryset = base_queryset

    if query:
        queryset = queryset.filter(
            Q(invoice_number__icontains=query)
            | Q(bank__icontains=query)
            | Q(payment_method__icontains=query)
        )
    if year.isdigit():
        queryset = queryset.filter(period__year=int(year))

    years = list(
        base_queryset.order_by("-period__year")
        .values_list("period__year", flat=True)
        .distinct()
    )
    totals = base_queryset.aggregate(
        count=Count("id"),
        amount=Coalesce(
            Sum("amount"),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
    )
    current_year = timezone.localdate().year
    page = Paginator(queryset, 9).get_page(request.GET.get("page"))
    return render(request, "driver/invoices.html", {
        **_driver_common_context(driver),
        "page": page,
        "query": query,
        "year": year,
        "years": years,
        "invoice_count": totals["count"],
        "total_invoiced": totals["amount"],
        "current_year": current_year,
        "current_year_count": base_queryset.filter(period__year=current_year).count(),
    })


@admin_required
def monthly_payment_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    bank_filter = request.GET.get("bank", "all")
    period_value = request.GET.get("period", "").strip()
    try:
        current_period = datetime.strptime(period_value, "%Y-%m").date().replace(day=1) if period_value else timezone.localdate().replace(day=1)
    except ValueError:
        current_period = timezone.localdate().replace(day=1)
    drivers = _profile_queryset("drivers").order_by("first_name", "last_name")
    if query:
        drivers = drivers.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
            | Q(email__icontains=query) | Q(identification_number__icontains=query)
            | Q(cedula__icontains=query)
        )
    current_payments = {
        payment.driver_id: payment
        for payment in DriverMonthlyPayment.objects.filter(period=current_period)
    }
    rows = []
    for driver in drivers:
        payment = current_payments.get(driver.id)
        row_status = payment.status if payment else "unpaid"
        if status != "all" and row_status != status:
            continue
        if bank_filter != "all" and (not payment or payment.bank != bank_filter):
            continue
        avatar_value = driver.profile_photo_url or driver.avatar_url
        rows.append({
            "driver": driver,
            "payment": payment,
            "status": row_status,
            "avatar_url": resolve_media_url(
                avatar_value, expires=900,
                preferred_buckets=(settings.SUPABASE_PUBLIC_BUCKET, settings.SUPABASE_PRIVATE_BUCKET),
            ) if avatar_value else "",
        })
    page = Paginator(rows, 10).get_page(request.GET.get("page"))
    counts = {
        "all": len(current_payments),
        "pending": sum(1 for p in current_payments.values() if p.status == "pending"),
        "approved": sum(1 for p in current_payments.values() if p.status == "approved"),
        "rejected": sum(1 for p in current_payments.values() if p.status == "rejected"),
        "unpaid": max(0, drivers.count() - len(current_payments)),
    }
    return render(request, "payments/list.html", {
        "page": page, "query": query, "status": status, "counts": counts,
        "period": current_period, "period_value": current_period.strftime("%Y-%m"),
        "bank_filter": bank_filter,
        "banks": PaymentBankAccount.objects.filter(is_active=True),
        "block_form": DriverBlockForm(),
    })


@admin_required
def monthly_payment_detail(request, payment_id):
    payment = get_object_or_404(DriverMonthlyPayment.objects.select_related("driver"), pk=payment_id)
    avatar_value = payment.driver.profile_photo_url or payment.driver.avatar_url
    invoice = DriverInvoice.objects.filter(payment=payment).first()
    return render(request, "payments/detail.html", {
        "payment": payment,
        "driver": payment.driver,
        "driver_avatar_url": resolve_media_url(
            avatar_value, expires=900,
            preferred_buckets=(settings.SUPABASE_PUBLIC_BUCKET, settings.SUPABASE_PRIVATE_BUCKET),
        ) if avatar_value else "",
        "invoice": invoice,
        "block_form": DriverBlockForm(initial={"reason": payment.driver.blocked_reason or ""}),
    })


@admin_required
@require_POST
def monthly_payment_review(request, payment_id, decision):
    payment = get_object_or_404(DriverMonthlyPayment.objects.select_related("driver"), pk=payment_id)
    if decision not in {"approve", "reject"}:
        raise Http404
    if decision == "reject" and not request.POST.get("notes", "").strip():
        messages.error(request, "Escribe el motivo del rechazo.")
        return redirect("panel:monthly_payment_detail", payment_id=payment.id)
    payment.status = DriverMonthlyPayment.STATUS_APPROVED if decision == "approve" else DriverMonthlyPayment.STATUS_REJECTED
    payment.admin_notes = request.POST.get("notes", "").strip() or None
    payment.reviewed_by = request.user.username
    payment.reviewed_at = timezone.now()
    payment.updated_at = payment.reviewed_at
    payment.save(update_fields=["status", "admin_notes", "reviewed_by", "reviewed_at", "updated_at"])
    title = "Mensualidad aprobada" if decision == "approve" else "Mensualidad rechazada"
    message = (
        f"Tu mensualidad de {payment.period:%m/%Y} fue aprobada."
        if decision == "approve"
        else f"Tu mensualidad de {payment.period:%m/%Y} fue rechazada: {payment.admin_notes}"
    )
    _notify_profile(payment.driver, title, message, "monthly_payment")
    audit(request, decision, "driver_monthly_payment", message, payment.id)
    messages.success(request, message)
    return redirect("panel:monthly_payment_detail", payment_id=payment.id)


@admin_required
@require_POST
def monthly_payment_physical(request, profile_id):
    driver = get_object_or_404(_profile_queryset("drivers"), pk=profile_id)
    period = timezone.localdate().replace(day=1)
    try:
        amount = Decimal(request.POST.get("amount", "0"))
    except Exception:
        amount = Decimal("0")
    if amount <= 0:
        messages.error(request, "Indica el valor recibido para registrar el pago físico.")
        return redirect("panel:monthly_payment_list")
    payment, created = DriverMonthlyPayment.objects.get_or_create(
        driver=driver,
        period=period,
        defaults={
            "id": uuid.uuid4(), "bank": "physical", "payment_method": "cash", "amount": amount,
            "status": DriverMonthlyPayment.STATUS_APPROVED, "reviewed_by": request.user.username,
            "reviewed_at": timezone.now(), "created_at": timezone.now(), "updated_at": timezone.now(),
        },
    )
    if not created:
        payment.status = DriverMonthlyPayment.STATUS_APPROVED
        payment.bank = "physical"
        payment.payment_method = "cash"
        payment.amount = amount
        payment.reviewed_by = request.user.username
        payment.reviewed_at = timezone.now()
        payment.updated_at = payment.reviewed_at
        payment.save(update_fields=["status", "bank", "payment_method", "amount", "reviewed_by", "reviewed_at", "updated_at"])
    _notify_profile(driver, "Mensualidad registrada", f"Tu pago físico de {period:%m/%Y} fue registrado.", "monthly_payment")
    messages.success(request, "Pago físico registrado y aprobado.")
    return redirect("panel:monthly_payment_list")


def _notify_profile(profile, title, message, notification_type):
    now = timezone.now()
    Notification.objects.create(
        id=uuid.uuid4(), user=profile, type=notification_type,
        title=title, message=message, is_read=False, created_at=now,
    )
    tokens = active_tokens_for_users([profile.id])
    send_push_notifications(tokens, title, message, {"type": notification_type})


@admin_required
@require_POST
def driver_payment_block(request, profile_id, action):
    driver = get_object_or_404(_profile_queryset("drivers"), pk=profile_id)
    if action == "unblock":
        driver.is_active = True
        driver.blocked_at = None
        driver.blocked_reason = None
        message = "Tu cuenta MOVIX fue habilitada nuevamente."
        title = "Cuenta habilitada"
    elif action == "block":
        form = DriverBlockForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Debes indicar el motivo del bloqueo.")
            return redirect(request.META.get("HTTP_REFERER") or "panel:monthly_payment_list")
        driver.is_active = False
        driver.blocked_at = timezone.now()
        driver.blocked_reason = form.cleaned_data["reason"]
        title = "Cuenta bloqueada"
        message = f"Tu cuenta MOVIX fue bloqueada. Motivo: {driver.blocked_reason}"
    else:
        raise Http404
    driver.updated_at = timezone.now()
    driver.save(update_fields=["is_active", "blocked_at", "blocked_reason", "updated_at"])
    _notify_profile(driver, title, message, "account_status")
    audit(request, action, "profile", message, driver.id)
    messages.success(request, message)
    return redirect(request.META.get("HTTP_REFERER") or "panel:monthly_payment_list")


@admin_required
def payment_bank_accounts(request):
    edit_id = request.GET.get("editar") or request.POST.get("bank_id")
    instance = get_object_or_404(PaymentBankAccount, pk=edit_id) if edit_id else None
    form = PaymentBankAccountForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        uploaded_values = []
        replacements = []
        try:
            account = form.save(commit=False)
            account.id = account.id or uuid.uuid4()
            account.created_at = account.created_at or timezone.now()
            account.updated_at = timezone.now()
            for field_name, model_field, public in (
                ("logo_file", "logo_url", True),
                ("qr_file", "qr_url", False),
            ):
                uploaded = form.cleaned_data.get(field_name)
                if not uploaded:
                    continue
                old_value = getattr(account, model_field, "")
                value = upload_to_supabase(
                    uploaded,
                    folder=f"payment-banks/{account.code}/{field_name}",
                    public=public,
                    images_only=True,
                )
                setattr(account, model_field, value)
                uploaded_values.append(value)
                replacements.append(old_value)
            account.save(force_insert=instance is None)
            for old_value in replacements:
                delete_storage_object(old_value)
            audit(request, "update" if instance else "create", "payment_bank", f"Configuró {account.name}", account.id)
            messages.success(request, f"Los datos de {account.name} fueron guardados.")
            return redirect("panel:payment_bank_accounts")
        except (ValidationError, DatabaseError) as exc:
            for value in uploaded_values:
                delete_storage_object(value)
            form.add_error(None, exc)
    accounts = list(PaymentBankAccount.objects.all())
    return render(request, "payments/banks.html", {
        "form": form,
        "editing_bank": instance,
        "accounts": accounts,
    })


@admin_required
@require_POST
def payment_bank_toggle(request, bank_id):
    account = get_object_or_404(PaymentBankAccount, pk=bank_id)
    account.is_active = not account.is_active
    account.updated_at = timezone.now()
    account.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"{account.name} ahora está {'visible' if account.is_active else 'oculto'} para los transportistas.")
    return redirect("panel:payment_bank_accounts")


def _storage_value_response(value, action, fallback_name, preferred_buckets):
    if action not in {"view", "download"} or not value or not is_safe_media_url(value):
        raise Http404
    url = resolve_media_url(value, expires=300, preferred_buckets=preferred_buckets)
    if not url:
        raise Http404("No se encontró el archivo en Supabase Storage.")
    try:
        upstream = requests.get(url, stream=True, timeout=(8, 40), allow_redirects=True)
        upstream.raise_for_status()
    except requests.RequestException as exc:
        raise Http404("Supabase no pudo entregar el archivo.") from exc
    filename = str(value).split("?", 1)[0].rstrip("/").split("/")[-1] or fallback_name
    content_type = (upstream.headers.get("Content-Type") or mimetypes.guess_type(filename)[0] or "application/octet-stream").split(";", 1)[0]

    def stream_file():
        try:
            yield from upstream.iter_content(chunk_size=64 * 1024)
        finally:
            upstream.close()

    response = StreamingHttpResponse(stream_file(), content_type=content_type)
    response["Content-Disposition"] = f'{"attachment" if action == "download" else "inline"}; filename="{filename.replace(chr(34), "")}"'
    response["Cache-Control"] = "private, max-age=60" if action == "view" else "no-store"
    if upstream.headers.get("Content-Length"):
        response["Content-Length"] = upstream.headers["Content-Length"]
    return response


@xframe_options_sameorigin
def payment_bank_asset(request, bank_id, asset, action="view"):
    is_admin = request.user.is_authenticated and request.user.is_staff
    is_driver = bool(request.session.get("portal_profile_id"))
    if not is_admin and not is_driver:
        raise PermissionDenied("Inicia sesión para consultar los datos bancarios.")
    account = get_object_or_404(PaymentBankAccount, pk=bank_id)
    if asset == "logo":
        value = account.logo_url
        preferred = (settings.SUPABASE_PUBLIC_BUCKET, settings.SUPABASE_PRIVATE_BUCKET)
    elif asset == "qr":
        value = account.qr_url
        preferred = (settings.SUPABASE_PRIVATE_BUCKET, settings.SUPABASE_PUBLIC_BUCKET)
    else:
        raise Http404
    return _storage_value_response(value, action, f"{account.code}-{asset}", preferred)


@admin_required
@require_POST
def monthly_payment_invoice(request, payment_id):
    payment = get_object_or_404(DriverMonthlyPayment.objects.select_related("driver"), pk=payment_id)
    if payment.status != DriverMonthlyPayment.STATUS_APPROVED:
        messages.error(request, "Primero debes aprobar la mensualidad.")
        return redirect("panel:monthly_payment_detail", payment_id=payment.id)
    if not payment.amount or payment.amount <= 0:
        messages.error(request, "Registra un valor mayor a cero antes de generar la factura.")
        return redirect("panel:monthly_payment_detail", payment_id=payment.id)
    number = f"MOVIX-{payment.period:%Y%m}-{str(payment.id).replace('-', '')[:8].upper()}"
    invoice, created = DriverInvoice.objects.get_or_create(
        payment=payment,
        defaults={
            "id": uuid.uuid4(),
            "invoice_number": number,
            "driver": payment.driver,
            "customer_name": payment.driver.full_name,
            "customer_email": payment.driver.email,
            "customer_identification": payment.driver.identity,
            "period": payment.period,
            "amount": payment.amount,
            "bank": payment.bank_label,
            "payment_method": payment.method_label,
            "status": "issued",
            "issued_at": timezone.now(),
            "created_by": request.user.username,
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
        },
    )
    try:
        pdf_bytes = build_monthly_invoice_pdf(invoice)
        if not invoice.pdf_url:
            pdf_file = ContentFile(pdf_bytes, name=f"{invoice.invoice_number}.pdf")
            pdf_file.content_type = "application/pdf"
            invoice.pdf_url = upload_to_supabase(
                pdf_file,
                folder=f"monthly-invoices/{invoice.driver_id}/{invoice.period:%Y-%m}",
                public=False,
                images_only=False,
            )
        email_sent, email_error = send_movix_email(
            invoice.customer_email,
            f"Factura de mensualidad {invoice.invoice_number}",
            f"Hola {invoice.customer_name}, adjuntamos tu factura de la mensualidad {invoice.period:%m/%Y} por USD {invoice.amount:.2f}.",
            f"{invoice.invoice_number}.pdf",
            pdf_bytes,
        )
        invoice.emailed_at = timezone.now() if email_sent else invoice.emailed_at
        invoice.updated_at = timezone.now()
        invoice.save(update_fields=["pdf_url", "emailed_at", "updated_at"])
        inbox, _ = DriverInboxMessage.objects.get_or_create(
            invoice=invoice,
            message_type="invoice",
            defaults={
                "id": uuid.uuid4(),
                "driver": invoice.driver,
                "title": f"Factura {invoice.invoice_number}",
                "body": f"Tu mensualidad de {invoice.period:%m/%Y} fue facturada correctamente.",
                "details": {"period": invoice.period.isoformat(), "amount": str(invoice.amount), "invoice_number": invoice.invoice_number},
                "is_read": False,
                "emailed_at": invoice.emailed_at,
                "created_by": request.user.username,
                "created_at": timezone.now(),
            },
        )
        _notify_profile(invoice.driver, "Factura disponible", f"La factura {invoice.invoice_number} ya está en tu buzón.", "invoice")
        audit(request, "issue", "driver_invoice", f"Emitió {invoice.invoice_number}", invoice.id)
        if email_sent:
            messages.success(request, "Factura generada, guardada en el buzón y enviada por correo.")
        else:
            messages.warning(request, f"Factura guardada en el buzón, pero el correo no salió: {email_error}")
    except (ValidationError, DatabaseError) as exc:
        if created and not invoice.pdf_url:
            invoice.delete()
        messages.error(request, str(exc))
    return redirect("panel:monthly_payment_detail", payment_id=payment.id)


@driver_portal_required
def driver_inbox(request):
    driver = _current_driver(request)
    message_type = request.GET.get("type", "all")
    read_filter = request.GET.get("read", "all")
    query = request.GET.get("q", "").strip()
    queryset = DriverInboxMessage.objects.filter(driver=driver).select_related("invoice")
    if message_type in dict(DriverInboxMessage.TYPE_CHOICES):
        queryset = queryset.filter(message_type=message_type)
    if read_filter == "unread":
        queryset = queryset.filter(is_read=False)
    elif read_filter == "read":
        queryset = queryset.filter(is_read=True)
    if query:
        queryset = queryset.filter(Q(title__icontains=query) | Q(body__icontains=query))
    page = Paginator(queryset, 10).get_page(request.GET.get("page"))
    return render(request, "driver/inbox.html", {
        **_driver_common_context(driver),
        "page": page,
        "message_type": message_type,
        "read_filter": read_filter,
        "query": query,
        "types": DriverInboxMessage.TYPE_CHOICES,
        "unread_count": DriverInboxMessage.objects.filter(driver=driver, is_read=False).count(),
    })


@driver_portal_required
def driver_inbox_detail(request, message_id):
    driver = _current_driver(request)
    inbox_message = get_object_or_404(
        DriverInboxMessage.objects.select_related("invoice"),
        pk=message_id,
        driver=driver,
    )
    if not inbox_message.is_read:
        inbox_message.is_read = True
        inbox_message.read_at = timezone.now()
        inbox_message.save(update_fields=["is_read", "read_at"])
    return render(request, "driver/inbox_detail.html", {
        **_driver_common_context(driver),
        "inbox_message": inbox_message,
    })


@admin_required
def admin_driver_messages(request):
    form = DriverInboxMessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        inbox_message = form.save(commit=False)
        inbox_message.id = uuid.uuid4()
        inbox_message.details = {}
        if form.cleaned_data.get("meeting_at"):
            inbox_message.details["meeting_at"] = form.cleaned_data["meeting_at"].isoformat()
        inbox_message.is_read = False
        inbox_message.created_by = request.user.username
        inbox_message.created_at = timezone.now()
        # Primero se conserva el mensaje interno. Un proveedor de correo caído
        # nunca debe hacer que el transportista pierda el aviso en su buzón.
        inbox_message.save(force_insert=True)
        email_sent, email_error = (False, "")
        if form.cleaned_data.get("send_email"):
            email_sent, email_error = send_movix_email(
                inbox_message.driver.email,
                inbox_message.title,
                inbox_message.body,
            )
            if email_sent:
                inbox_message.emailed_at = timezone.now()
                inbox_message.save(update_fields=["emailed_at"])
        _notify_profile(inbox_message.driver, inbox_message.title, inbox_message.body, inbox_message.message_type)
        audit(request, "send", "driver_inbox_message", f"Envió mensaje a {inbox_message.driver.full_name}", inbox_message.id)
        if form.cleaned_data.get("send_email") and not email_sent:
            messages.warning(request, f"Mensaje guardado y notificado; el correo no salió: {email_error}")
        else:
            messages.success(request, "Mensaje enviado al buzón, notificaciones y correo configurado.")
        return redirect("panel:admin_driver_messages")

    query = request.GET.get("q", "").strip()
    message_type = request.GET.get("type", "all")
    queryset = DriverInboxMessage.objects.select_related("driver", "invoice")
    if query:
        queryset = queryset.filter(
            Q(driver__first_name__icontains=query) | Q(driver__last_name__icontains=query)
            | Q(driver__email__icontains=query) | Q(title__icontains=query)
        )
    if message_type in dict(DriverInboxMessage.TYPE_CHOICES):
        queryset = queryset.filter(message_type=message_type)
    page = Paginator(queryset, 12).get_page(request.GET.get("page"))
    return render(request, "payments/messages.html", {
        "form": form,
        "page": page,
        "query": query,
        "message_type": message_type,
        "types": DriverInboxMessage.TYPE_CHOICES,
    })


@xframe_options_sameorigin
def driver_invoice_file(request, invoice_id, action="view"):
    invoice = get_object_or_404(DriverInvoice.objects.select_related("driver"), pk=invoice_id)
    is_admin = request.user.is_authenticated and request.user.is_staff
    is_owner = str(request.session.get("portal_profile_id") or "") == str(invoice.driver_id)
    if not is_admin and not is_owner:
        raise PermissionDenied("No puedes consultar esta factura.")
    return _storage_value_response(
        invoice.pdf_url,
        action,
        f"{invoice.invoice_number}.pdf",
        (settings.SUPABASE_PRIVATE_BUCKET, settings.SUPABASE_PUBLIC_BUCKET),
    )


@admin_required
def contact_request_list(request):
    queryset = ContactRequest.objects.all()
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    if query:
        queryset = queryset.filter(
            Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
            | Q(subject__icontains=query)
            | Q(message__icontains=query)
        )
    if status in dict(ContactRequest.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    counts = ContactRequest.objects.aggregate(
        total=Count("id"),
        new=Count("id", filter=Q(status=ContactRequest.STATUS_NEW)),
        read=Count("id", filter=Q(status=ContactRequest.STATUS_READ)),
        responded=Count("id", filter=Q(status=ContactRequest.STATUS_RESPONDED)),
        closed=Count("id", filter=Q(status=ContactRequest.STATUS_CLOSED)),
    )
    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "panel/contact_request_list.html",
        {"page": page, "query": query, "status": status, "counts": counts},
    )


@admin_required
def contact_request_detail(request, request_id):
    contact = get_object_or_404(ContactRequest, pk=request_id)
    if contact.status == ContactRequest.STATUS_NEW:
        contact.status = ContactRequest.STATUS_READ
        contact.save(update_fields=["status", "updated_at"])
        cache.delete("movix-new-contact-count")

    form = ContactResponseForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        contact = form.save(commit=False)
        email_body = (
            f"Hola {contact.full_name},\n\n{contact.admin_response.strip()}\n\n"
            "Saludos,\nEquipo MOVIX · Loja, Ecuador"
        )
        email_sent, email_error = send_movix_email(
            contact.email,
            f"Respuesta MOVIX: {contact.subject}",
            email_body,
        )
        if email_sent:
            contact.status = ContactRequest.STATUS_RESPONDED
            contact.responded_by = request.user.get_full_name() or request.user.username
            contact.responded_at = timezone.now()
        contact.save()
        cache.delete("movix-new-contact-count")
        if email_sent:
            audit(request, "respond", "contact_request", f"Respondió la solicitud de {contact.full_name}", contact.id)
            messages.success(request, f"Respuesta enviada correctamente a {contact.email}.")
        else:
            messages.warning(
                request,
                f"La respuesta quedó guardada, pero Gmail no pudo enviarla: {email_error}",
            )
        return redirect("panel:contact_request_detail", request_id=contact.id)

    return render(
        request,
        "panel/contact_request_detail.html",
        {"contact": contact, "form": form},
    )


@admin_required
@require_POST
def contact_request_status(request, request_id, status):
    contact = get_object_or_404(ContactRequest, pk=request_id)
    allowed = dict(ContactRequest.STATUS_CHOICES)
    if status not in allowed:
        raise Http404("Estado no válido")
    contact.status = status
    contact.save(update_fields=["status", "updated_at"])
    cache.delete("movix-new-contact-count")
    audit(request, "status", "contact_request", f"Marcó la solicitud como {allowed[status].lower()}", contact.id)
    messages.success(request, f"Solicitud marcada como {allowed[status].lower()}.")
    return redirect("panel:contact_request_detail", request_id=contact.id)


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
    summary_keys = ("identification", "vehicle") if profile.is_driver else ("identification",)
    return render(request, "panel/profile_detail.html", {
        "kind": kind,
        "config": config,
        "profile": profile,
        "reviews": reviews,
        "ride_count": ride_count,
        "summary_documents": _profile_document_items(profile, summary_keys),
    })


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
    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(request, "panel/verification_list.html", {
        "profiles": page.object_list,
        "page": page,
        "counts": counts,
        "query": query,
        "status": status,
        "kind_filter": kind,
    })


@admin_required
def verification_detail(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id)
    documents = _profile_document_items(profile)
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


@xframe_options_sameorigin
def document_access(request, profile_id, document_key, action="view"):
    profile = get_object_or_404(Profile, pk=profile_id)
    is_admin = request.user.is_authenticated and request.user.is_staff
    is_owner = str(request.session.get("portal_profile_id") or "") == str(profile.id)
    if not is_admin and not is_owner:
        raise PermissionDenied("No puedes consultar documentos de otro perfil.")
    if document_key not in DOCUMENT_FIELDS:
        raise Http404
    field_name, label = DOCUMENT_FIELDS[document_key]
    value = getattr(profile, field_name, "")
    if document_key == "profile" and not value:
        value = profile.avatar_url
    if not value or not is_safe_media_url(value):
        messages.error(request, "El archivo no existe o su origen no está permitido.")
        return redirect("panel:verification_detail", profile_id=profile.id)
    preferred_buckets = (
        (settings.SUPABASE_PUBLIC_BUCKET, settings.SUPABASE_PRIVATE_BUCKET)
        if document_key in PUBLIC_DOCUMENT_KEYS
        else (settings.SUPABASE_PRIVATE_BUCKET, settings.SUPABASE_PUBLIC_BUCKET)
    )
    url = resolve_media_url(value, expires=300, preferred_buckets=preferred_buckets)
    if not url:
        if action == "view":
            svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420" viewBox="0 0 720 420">
            <rect width="720" height="420" rx="22" fill="#edf8ff"/><g fill="none" stroke="#2d6bea" stroke-width="10" stroke-linecap="round"><rect x="290" y="105" width="140" height="120" rx="18"/><path d="m305 207 42-45 35 32 24-25 20 19"/><path d="M300 292h120"/></g><text x="360" y="335" text-anchor="middle" font-family="Arial,sans-serif" font-size="23" font-weight="700" fill="#183153">No se encontró {escape(label)}</text><text x="360" y="370" text-anchor="middle" font-family="Arial,sans-serif" font-size="16" fill="#6c7f9c">Revisa la ruta y el bucket guardados en Supabase</text></svg>"""
            placeholder = HttpResponse(svg, content_type="image/svg+xml")
            placeholder["X-Movix-Media-Status"] = "storage-object-not-found"
            placeholder["Cache-Control"] = "no-store"
            return placeholder
        messages.error(request, "El campo existe, pero no coincide con ningún objeto accesible de Supabase Storage.")
        return redirect("panel:verification_detail", profile_id=profile.id)
    # El navegador no se redirige directamente a Supabase. Django descarga el
    # objeto con la URL pública/firmada recién generada y lo sirve desde el mismo
    # dominio del panel. Esto evita enlaces firmados vencidos, bloqueos del
    # navegador y diferencias entre buckets públicos y privados.
    try:
        upstream = requests.get(url, stream=True, timeout=(8, 40), allow_redirects=True)
    except requests.RequestException:
        upstream = None

    if upstream is None or upstream.status_code != 200:
        if upstream is not None:
            upstream.close()
        if action == "view":
            svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420" viewBox="0 0 720 420">
            <rect width="720" height="420" rx="22" fill="#edf8ff"/><g fill="none" stroke="#ef4444" stroke-width="10" stroke-linecap="round"><rect x="290" y="105" width="140" height="120" rx="18"/><path d="m305 207 42-45 35 32 24-25 20 19"/><path d="M300 292h120"/></g><text x="360" y="335" text-anchor="middle" font-family="Arial,sans-serif" font-size="23" font-weight="700" fill="#183153">Supabase no entregó {escape(label)}</text><text x="360" y="370" text-anchor="middle" font-family="Arial,sans-serif" font-size="16" fill="#6c7f9c">Comprueba SUPABASE_SERVICE_ROLE_KEY y la ruta del objeto</text></svg>"""
            placeholder = HttpResponse(svg, content_type="image/svg+xml")
            placeholder["X-Movix-Media-Status"] = "storage-download-failed"
            placeholder["Cache-Control"] = "no-store"
            return placeholder
        messages.error(request, "Supabase encontró la ruta, pero no permitió descargar el archivo.")
        return redirect("panel:verification_detail", profile_id=profile.id)

    raw_name = str(value).split("?", 1)[0].rstrip("/").split("/")[-1]
    filename = raw_name or url.split("?", 1)[0].rstrip("/").split("/")[-1] or f"{label}.bin"
    content_type = (upstream.headers.get("Content-Type") or "application/octet-stream").split(";", 1)[0].strip()
    if content_type == "application/octet-stream":
        content_type = mimetypes.guess_type(filename)[0] or content_type
    # Una respuesta JSON en este punto corresponde a un error de Storage, no a
    # una imagen válida. No se envía al elemento <img> del navegador.
    if content_type in {"application/json", "text/json"}:
        upstream.close()
        if action == "view":
            placeholder = HttpResponse(
                '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420"><rect width="100%" height="100%" rx="22" fill="#edf8ff"/><text x="50%" y="48%" text-anchor="middle" font-family="Arial" font-size="24" font-weight="700" fill="#183153">El archivo no pudo abrirse</text><text x="50%" y="57%" text-anchor="middle" font-family="Arial" font-size="16" fill="#6c7f9c">Supabase devolvió una respuesta de permisos</text></svg>',
                content_type="image/svg+xml",
            )
            placeholder["X-Movix-Media-Status"] = "storage-invalid-response"
            placeholder["Cache-Control"] = "no-store"
            return placeholder
        messages.error(request, "Supabase devolvió una respuesta de permisos en lugar del archivo.")
        return redirect("panel:verification_detail", profile_id=profile.id)

    def stream_file():
        try:
            yield from upstream.iter_content(chunk_size=64 * 1024)
        finally:
            upstream.close()

    response = StreamingHttpResponse(stream_file(), content_type=content_type)
    disposition = "attachment" if action == "download" else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{filename.replace(chr(34), "")}"'
    response["Cache-Control"] = "private, max-age=60" if action == "view" else "no-store"
    response["X-Movix-Media-Status"] = "proxied"
    if upstream.headers.get("Content-Length"):
        response["Content-Length"] = upstream.headers["Content-Length"]
    return response


@xframe_options_sameorigin
def monthly_payment_receipt(request, payment_id, action="view"):
    payment = get_object_or_404(DriverMonthlyPayment.objects.select_related("driver"), pk=payment_id)
    is_admin = request.user.is_authenticated and request.user.is_staff
    is_owner = str(request.session.get("portal_profile_id") or "") == str(payment.driver_id)
    if not is_admin and not is_owner:
        raise PermissionDenied("No puedes consultar este comprobante.")
    if action not in {"view", "download"} or not payment.receipt_url or not is_safe_media_url(payment.receipt_url):
        raise Http404
    url = resolve_media_url(
        payment.receipt_url,
        expires=300,
        preferred_buckets=(settings.SUPABASE_PRIVATE_BUCKET, settings.SUPABASE_PUBLIC_BUCKET),
    )
    if not url:
        raise Http404("No se encontró el comprobante en Supabase Storage.")
    try:
        upstream = requests.get(url, stream=True, timeout=(8, 40), allow_redirects=True)
        upstream.raise_for_status()
    except requests.RequestException as exc:
        raise Http404("Supabase no pudo entregar el comprobante.") from exc
    filename = str(payment.receipt_url).split("?", 1)[0].rstrip("/").split("/")[-1] or "comprobante"
    content_type = (upstream.headers.get("Content-Type") or mimetypes.guess_type(filename)[0] or "application/octet-stream").split(";", 1)[0]

    def stream_file():
        try:
            yield from upstream.iter_content(chunk_size=64 * 1024)
        finally:
            upstream.close()

    response = StreamingHttpResponse(stream_file(), content_type=content_type)
    disposition = "attachment" if action == "download" else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{filename.replace(chr(34), "")}"'
    response["Cache-Control"] = "private, max-age=60" if action == "view" else "no-store"
    if upstream.headers.get("Content-Length"):
        response["Content-Length"] = upstream.headers["Content-Length"]
    return response


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
    editing = request.GET.get("editar") == "1" or request.POST.get("action") == "profile"
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
    return render(
        request,
        "panel/admin_profile.html",
        {
            "admin_profile": admin_profile,
            "profile_form": profile_form,
            "password_form": password_form,
            "stats": stats,
            "editing": editing,
        },
    )


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
        ("Mensualidades", "panel:monthly_payment_list"),
        ("Bancos y cuentas", "panel:payment_bank_accounts"),
        ("Mensajes transportistas", "panel:admin_driver_messages"),
        ("Perfil", "panel:admin_profile"), ("Configuración", "panel:settings"),
    ]
    results = [item for item in modules if len(query) >= 2 and query in item[0].lower()]
    return render(request, "panel/search.html", {"query": query, "module_results": results})
