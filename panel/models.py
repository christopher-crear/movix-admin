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

    @property
    def vehicle_type_label(self):
        value = str(self.vehicle_type or "").strip()
        return {
            "camioneta": "Camioneta",
            "camion_pequeno": "Camión pequeño",
            "camion pequeño": "Camión pequeño",
            "camión pequeño": "Camión pequeño",
            "camion_mediano": "Camión mediano",
            "camion mediano": "Camión mediano",
            "camión mediano": "Camión mediano",
        }.get(value.lower(), value or "Vehículo sin especificar")

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

    @property
    def effective_price(self):
        return self.driver_price if self.driver_price is not None else self.price

    @property
    def status_label(self):
        value = (self.status or "").lower()
        labels = {
            "solicitada": "Solicitada",
            "aceptada": "Aceptada",
            "accepted": "Aceptada",
            "en_camino": "En camino",
            "en curso": "En curso",
            "in_progress": "En curso",
            "completada": "Completada",
            "completado": "Completada",
            "completed": "Completada",
            "finalizada": "Completada",
            "finalizado": "Completada",
            "cancelada": "Cancelada",
            "cancelado": "Cancelada",
            "cancelled": "Cancelada",
            "canceled": "Cancelada",
        }
        return labels.get(value, (self.status or "Sin estado").replace("_", " ").title())

    @property
    def is_completed(self):
        return (self.status or "").lower() in {"completada", "completado", "completed", "finalizada", "finalizado"}

    @property
    def is_cancelled(self):
        return (self.status or "").lower() in {"cancelada", "cancelado", "cancelled", "canceled"}


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


class DriverMonthlyPayment(models.Model):
    """Mensualidades declaradas por los transportistas en Supabase."""

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_APPROVED, "Aprobado"),
        (STATUS_REJECTED, "Rechazado"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    driver = models.ForeignKey(
        Profile,
        models.DO_NOTHING,
        db_column="driver_id",
        related_name="monthly_payments",
    )
    period = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    bank = models.TextField()
    payment_method = models.TextField(default="transfer")
    receipt_url = models.TextField(blank=True, null=True)
    status = models.TextField(default=STATUS_PENDING)
    admin_notes = models.TextField(blank=True, null=True)
    reviewed_by = models.TextField(blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "driver_monthly_payments"
        ordering = ["-period", "-created_at"]

    @property
    def status_label(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def method_label(self):
        return {"transfer": "Transferencia", "deposit": "Depósito", "cash": "Efectivo"}.get(
            self.payment_method, self.payment_method
        )

    @property
    def bank_label(self):
        return {
            "banco_loja": "Banco de Loja",
            "banco_pichincha": "Banco Pichincha",
            "coopego": "Banco Coopego",
            "jep": "Cooperativa JEP",
            "physical": "Pago físico",
        }.get(self.bank, self.bank)


class PaymentBankAccount(models.Model):
    """Cuentas de cobro configuradas por el administrador en Supabase."""

    BANK_CHOICES = [
        ("banco_loja", "Banco de Loja"),
        ("banco_pichincha", "Banco Pichincha"),
        ("coopego", "Banco Coopego"),
        ("jep", "Cooperativa JEP"),
    ]
    ACCOUNT_TYPE_CHOICES = [
        ("savings", "Ahorros"),
        ("checking", "Corriente"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    code = models.TextField(unique=True, choices=BANK_CHOICES)
    account_holder = models.TextField()
    account_number = models.TextField()
    account_type = models.TextField(default="savings", choices=ACCOUNT_TYPE_CHOICES)
    identification_number = models.TextField(blank=True, null=True)
    instructions = models.TextField(blank=True, null=True)
    logo_url = models.TextField(blank=True, null=True)
    qr_url = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "payment_bank_accounts"
        ordering = ["sort_order", "code"]

    @property
    def name(self):
        return dict(self.BANK_CHOICES).get(self.code, self.code)

    @property
    def account_type_label(self):
        return dict(self.ACCOUNT_TYPE_CHOICES).get(self.account_type, self.account_type)

    @property
    def default_logo(self):
        return {
            "banco_loja": "img/banks/banco-loja.svg",
            "banco_pichincha": "img/banks/banco-pichincha.svg",
            "coopego": "img/banks/coopego.svg",
            "jep": "img/banks/jep.svg",
        }.get(self.code, "img/logo-mark.svg")

    def __str__(self):
        return self.name


class DriverInvoice(models.Model):
    """Factura/recibo generado al aprobar una mensualidad."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    invoice_number = models.TextField(unique=True)
    payment = models.OneToOneField(
        DriverMonthlyPayment,
        models.DO_NOTHING,
        db_column="payment_id",
        related_name="invoice",
    )
    driver = models.ForeignKey(
        Profile,
        models.DO_NOTHING,
        db_column="driver_id",
        related_name="monthly_invoices",
    )
    customer_name = models.TextField()
    customer_email = models.TextField(blank=True, null=True)
    customer_identification = models.TextField(blank=True, null=True)
    period = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    bank = models.TextField()
    payment_method = models.TextField()
    pdf_url = models.TextField(blank=True, null=True)
    status = models.TextField(default="issued")
    issued_at = models.DateTimeField(blank=True, null=True)
    emailed_at = models.DateTimeField(blank=True, null=True)
    created_by = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "driver_invoices"
        ordering = ["-issued_at", "-created_at"]

    def __str__(self):
        return self.invoice_number


class DriverInboxMessage(models.Model):
    """Buzón persistente del transportista, visible también para la app móvil."""

    TYPE_CHOICES = [
        ("invoice", "Factura"),
        ("meeting", "Reunión"),
        ("payment", "Pago"),
        ("account", "Cuenta"),
        ("general", "General"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    driver = models.ForeignKey(
        Profile,
        models.DO_NOTHING,
        db_column="driver_id",
        related_name="inbox_messages",
    )
    message_type = models.TextField(default="general", choices=TYPE_CHOICES)
    title = models.TextField()
    body = models.TextField()
    invoice = models.ForeignKey(
        DriverInvoice,
        models.DO_NOTHING,
        db_column="invoice_id",
        related_name="messages",
        blank=True,
        null=True,
    )
    details = models.JSONField(default=dict)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    emailed_at = models.DateTimeField(blank=True, null=True)
    created_by = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "driver_inbox_messages"
        ordering = ["-created_at"]

    @property
    def type_label(self):
        return dict(self.TYPE_CHOICES).get(self.message_type, self.message_type)

    def __str__(self):
        return f"{self.driver.full_name} · {self.title}"


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
