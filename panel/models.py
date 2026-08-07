import uuid

from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    """Tabla existente `public.profiles` usada por la aplicación móvil."""

    id = models.UUIDField(primary_key=True)
    role = models.TextField(default="cliente")
    first_name = models.TextField(blank=True, null=True)
    last_name = models.TextField(blank=True, null=True)
    email = models.TextField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)
    cedula = models.TextField(blank=True, null=True)
    license_number = models.TextField(blank=True, null=True)
    vehicle_plate = models.TextField(blank=True, null=True)
    load_capacity = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    vehicle_year = models.IntegerField(blank=True, null=True)
    vehicle_type = models.TextField(blank=True, null=True)
    avatar_url = models.TextField(blank=True, null=True)
    vehicle_photo_url = models.TextField(blank=True, null=True)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_available = models.BooleanField(default=False)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5)
    completed_trips = models.IntegerField(default=0)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    identification_number = models.TextField(blank=True, null=True)
    profile_photo_url = models.TextField(blank=True, null=True)
    profile_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)
    experience_years = models.IntegerField(default=0)
    license_photo_url = models.TextField(blank=True, null=True)
    registration_photo_url = models.TextField(blank=True, null=True)
    insurance_photo_url = models.TextField(blank=True, null=True)
    license_verified = models.BooleanField(default=False)
    registration_verified = models.BooleanField(default=False)
    insurance_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True, null=True)
    verified_by = models.UUIDField(blank=True, null=True)

    # Columnas añadidas por sql/supabase_panel.sql.
    is_active = models.BooleanField(default=True)
    blocked_at = models.DateTimeField(blank=True, null=True)
    blocked_reason = models.TextField(blank=True, null=True)
    identification_photo_url = models.TextField(blank=True, null=True)
    verification_status = models.TextField(default="pending")
    verification_rejection_reason = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "profiles"
        ordering = ["-created_at"]

    @property
    def full_name(self):
        value = " ".join(part for part in [self.first_name, self.last_name] if part)
        return value or self.email or str(self.id)

    @property
    def initials(self):
        parts = [part for part in [self.first_name, self.last_name] if part]
        return "".join(part[0].upper() for part in parts[:2]) or "MV"

    @property
    def identity(self):
        return self.identification_number or self.cedula or "Sin identificación"

    @property
    def is_driver(self):
        return (self.role or "").lower() in {"driver", "conductor", "transportista"}

    @property
    def effective_verification_status(self):
        """Compatibilidad con perfiles creados antes de `verification_status`."""
        if self.profile_verified or self.verified:
            return "approved"
        if self.verification_status in {"pending", "approved", "rejected"}:
            return self.verification_status
        return "pending"

    @property
    def verification_label(self):
        return {
            "approved": "Aprobado",
            "rejected": "Rechazado",
            "pending": "Pendiente",
        }[self.effective_verification_status]

    @property
    def has_profile_photo(self):
        return bool(self.profile_photo_url or self.avatar_url)

    @property
    def status_label(self):
        if not self.is_active:
            return "Bloqueado"
        if self.is_driver and not self.is_available:
            return "No disponible"
        return "Activo"

    def __str__(self):
        return self.full_name


class Ride(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    client = models.ForeignKey(Profile, models.DO_NOTHING, db_column="client_id", related_name="requested_rides")
    driver = models.ForeignKey(Profile, models.DO_NOTHING, db_column="driver_id", related_name="assigned_rides", blank=True, null=True)
    service_type = models.TextField(default="transporte")
    origin_address = models.TextField()
    destination_address = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.TextField(default="solicitada")
    created_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    vehicle_type = models.TextField(blank=True, null=True)
    cargo_type = models.TextField(blank=True, null=True)
    cargo_description = models.TextField(blank=True, null=True)
    weight_kg = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    dimensions = models.TextField(blank=True, null=True)
    observations = models.TextField(blank=True, null=True)
    needs_helpers = models.BooleanField(default=False)
    helpers_count = models.IntegerField(default=0)
    distance_km = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    estimated_minutes = models.IntegerField(blank=True, null=True)
    payment_method = models.TextField(blank=True, null=True)
    payment_provider = models.TextField(blank=True, null=True)
    origin_latitude = models.FloatField(blank=True, null=True)
    origin_longitude = models.FloatField(blank=True, null=True)
    destination_latitude = models.FloatField(blank=True, null=True)
    destination_longitude = models.FloatField(blank=True, null=True)
    driver_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "rides"


class DriverReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    ride = models.ForeignKey(Ride, models.DO_NOTHING, db_column="ride_id")
    client = models.ForeignKey(Profile, models.DO_NOTHING, db_column="client_id", related_name="reviews_written")
    driver = models.ForeignKey(Profile, models.DO_NOTHING, db_column="driver_id", related_name="driver_reviews")
    rating = models.SmallIntegerField()
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "driver_reviews"
        ordering = ["-created_at"]


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(Profile, models.DO_NOTHING, db_column="user_id", related_name="notifications")
    type = models.TextField(default="general")
    title = models.TextField()
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "notifications"
        ordering = ["-created_at"]


class Advertisement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    title = models.TextField()
    description = models.TextField(blank=True, null=True)
    image_url = models.TextField()
    target_url = models.TextField(blank=True, null=True)
    audience = models.TextField(default="all")
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    created_by = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "advertisements"
        ordering = ["-created_at"]


class NotificationCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    audience = models.TextField()
    recipient = models.ForeignKey(Profile, models.DO_NOTHING, db_column="recipient_id", blank=True, null=True)
    title = models.TextField()
    message = models.TextField()
    total_recipients = models.IntegerField(default=0)
    push_sent = models.IntegerField(default=0)
    status = models.TextField(default="stored")
    error_message = models.TextField(blank=True, null=True)
    created_by = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "admin_notification_campaigns"
        ordering = ["-created_at"]


class DeviceToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(Profile, models.DO_NOTHING, db_column="user_id", related_name="device_tokens")
    token = models.TextField(unique=True)
    platform = models.TextField(default="unknown")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "device_tokens"


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    admin_username = models.TextField()
    action = models.TextField()
    entity_type = models.TextField()
    entity_id = models.TextField(blank=True, null=True)
    description = models.TextField()
    metadata = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "admin_audit_logs"
        ordering = ["-created_at"]


class SystemSetting(models.Model):
    key = models.TextField(primary_key=True)
    value = models.JSONField(default=dict)
    updated_by = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "admin_settings"


class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="movix_profile")
    phone = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=120, blank=True, default="Loja")
    avatar_url = models.TextField(blank=True)
    cover_url = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class ContactRequest(models.Model):
    """Solicitud enviada desde la página pública de MOVIX."""

    STATUS_NEW = "new"
    STATUS_READ = "read"
    STATUS_RESPONDED = "responded"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "Nueva"),
        (STATUS_READ, "Leída"),
        (STATUS_RESPONDED, "Respondida"),
        (STATUS_CLOSED, "Cerrada"),
    ]
    TYPE_CHOICES = [
        ("service", "Solicitar un transporte"),
        ("driver", "Quiero trabajar con MOVIX"),
        ("company", "Convenio para empresa"),
        ("support", "Ayuda o soporte"),
        ("other", "Otra consulta"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=160)
    email = models.EmailField(max_length=254)
    phone = models.CharField(max_length=30, blank=True)
    request_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default="service")
    subject = models.CharField(max_length=180)
    message = models.TextField(max_length=2000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    admin_response = models.TextField(max_length=4000, blank=True)
    responded_by = models.CharField(max_length=150, blank=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contact_requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="contact_status_created_idx"),
            models.Index(fields=["email"], name="contact_email_idx"),
        ]

    @property
    def status_label(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def initials(self):
        parts = [part for part in self.full_name.split() if part]
        return "".join(part[0].upper() for part in parts[:2]) or "MV"

    def __str__(self):
        return f"{self.full_name} · {self.subject}"
