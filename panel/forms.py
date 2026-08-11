from django import forms
from django.contrib.auth.models import User

from .models import (
    AdminProfile,
    Advertisement,
    ContactRequest,
    DriverInboxMessage,
    DriverMonthlyPayment,
    PaymentBankAccount,
    Profile,
)


INPUT_CLASS = "form-control"

VEHICLE_TYPE_CHOICES = [
    ("camioneta", "Camioneta"),
    ("camion_pequeno", "Camión pequeño"),
    ("camion_mediano", "Camión mediano"),
]


class StyledFormMixin:
    def apply_styles(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", INPUT_CLASS)


class ProfileForm(StyledFormMixin, forms.ModelForm):
    identification_file = forms.FileField(label="Foto de la cédula", required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}))
    profile_file = forms.ImageField(label="Foto de perfil", required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))
    vehicle_file = forms.ImageField(label="Foto del vehículo", required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))
    license_file = forms.FileField(label="Licencia de conducir", required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}))
    registration_file = forms.FileField(label="Matrícula vehicular", required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}))
    insurance_file = forms.FileField(label="Seguro vehicular", required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}))

    class Meta:
        model = Profile
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "identification_number",
            "license_number",
            "vehicle_plate",
            "load_capacity",
            "vehicle_year",
            "vehicle_type",
            "experience_years",
            "is_available",
        ]
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Correo electrónico",
            "phone": "Celular",
            "identification_number": "Cédula de identidad",
            "license_number": "Número de licencia",
            "vehicle_plate": "Placa del vehículo",
            "load_capacity": "Capacidad de carga (kg)",
            "vehicle_year": "Año del vehículo",
            "vehicle_type": "Tipo de vehículo",
            "experience_years": "Años de experiencia",
            "is_available": "Disponible para servicios",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"maxlength": 80, "autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"maxlength": 80, "autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"maxlength": 160, "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"maxlength": 20, "inputmode": "tel", "autocomplete": "tel"}),
            "identification_number": forms.TextInput(attrs={"maxlength": 10, "inputmode": "numeric"}),
            "license_number": forms.TextInput(attrs={"maxlength": 40}),
            "vehicle_plate": forms.TextInput(attrs={"maxlength": 20}),
            "load_capacity": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "vehicle_year": forms.NumberInput(attrs={"min": 1950, "max": 2100, "inputmode": "numeric"}),
            "vehicle_type": forms.Select(choices=VEHICLE_TYPE_CHOICES),
            "experience_years": forms.NumberInput(attrs={"min": 0, "max": 80, "inputmode": "numeric"}),
        }

    def __init__(self, *args, role="cliente", **kwargs):
        super().__init__(*args, **kwargs)
        self.role = role
        if role not in {"driver", "conductor", "transportista"}:
            for name in [
                "license_number",
                "vehicle_plate",
                "load_capacity",
                "vehicle_year",
                "vehicle_type",
                "experience_years",
                "is_available",
                "vehicle_file",
                "license_file",
                "registration_file",
                "insurance_file",
            ]:
                self.fields.pop(name, None)
        elif "vehicle_type" in self.fields:
            aliases = {
                "camioneta": "camioneta",
                "camión pequeño": "camion_pequeno",
                "camion pequeño": "camion_pequeno",
                "camion_pequeno": "camion_pequeno",
                "camión mediano": "camion_mediano",
                "camion mediano": "camion_mediano",
                "camion_mediano": "camion_mediano",
            }
            current = str(getattr(self.instance, "vehicle_type", "") or self.initial.get("vehicle_type") or "").strip().lower()
            if current in aliases:
                self.initial["vehicle_type"] = aliases[current]
        self.apply_styles()

    def clean_identification_number(self):
        value = (self.cleaned_data.get("identification_number") or "").strip()
        if value and (not value.isdigit() or len(value) != 10):
            raise forms.ValidationError("La cédula debe contener exactamente 10 dígitos.")
        return value or None

    def clean_vehicle_type(self):
        value = self.cleaned_data.get("vehicle_type")
        allowed = {choice[0] for choice in VEHICLE_TYPE_CHOICES}
        if self.role in {"driver", "conductor", "transportista"} and value not in allowed:
            raise forms.ValidationError("Selecciona Camioneta, Camión pequeño o Camión mediano.")
        return value


class ProfileCreateForm(ProfileForm):
    password = forms.CharField(label="Contraseña temporal", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), min_length=8)
    password_confirm = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["first_name", "last_name", "email", "phone", "identification_number"]:
            self.fields[name].required = True
        if self.role in {"driver", "conductor", "transportista"}:
            for name in ["license_number", "vehicle_plate", "load_capacity", "vehicle_year", "vehicle_type"]:
                self.fields[name].required = True

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("password_confirm"):
            self.add_error("password_confirm", "Las contraseñas no coinciden.")
        return cleaned


class DriverSelfProfileForm(ProfileForm):
    """Campos que un transportista puede actualizar en su propio perfil."""

    def __init__(self, *args, **kwargs):
        kwargs.pop("role", None)
        super().__init__(*args, role="transportista", **kwargs)
        # El correo y la cédula identifican la cuenta de Supabase y solo se
        # cambian mediante un flujo de verificación administrativa.
        self.fields.pop("email", None)
        self.fields.pop("identification_number", None)
        # El archivo de la cédula sí puede renovarse desde el portal. El número
        # permanece protegido para evitar cambiar la identidad de la cuenta.


class DriverMonthlyPaymentForm(StyledFormMixin, forms.ModelForm):
    BANK_CHOICES = [
        ("banco_loja", "Banco de Loja"),
        ("banco_pichincha", "Banco Pichincha"),
        ("coopego", "Banco Coopego"),
        ("jep", "Cooperativa JEP"),
    ]
    METHOD_CHOICES = [
        ("transfer", "Transferencia bancaria"),
        ("deposit", "Depósito bancario"),
        ("cash", "Pago físico"),
    ]

    receipt = forms.FileField(
        label="Comprobante",
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}),
    )

    class Meta:
        model = DriverMonthlyPayment
        fields = ["period", "amount", "bank", "payment_method"]
        labels = {
            "period": "Mes que estás pagando",
            "amount": "Valor pagado (USD)",
            "bank": "Banco utilizado",
            "payment_method": "Tipo de pago",
        }
        widgets = {
            "period": forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01", "inputmode": "decimal"}),
            "bank": forms.Select(),
            "payment_method": forms.Select(),
        }

    def __init__(self, *args, bank_accounts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["period"].input_formats = ["%Y-%m", "%Y-%m-%d"]
        # Cuando la vista entrega explícitamente las cuentas (aunque sea una
        # lista vacía), solo se permiten bancos configurados y visibles por el
        # administrador. El fallback conserva compatibilidad con formularios
        # instanciados fuera del portal, como pruebas y comandos internos.
        if bank_accounts is None:
            bank_choices = list(self.BANK_CHOICES)
        else:
            bank_choices = [
                (account.code, account.name) for account in bank_accounts
            ]
        self.available_bank_codes = {code for code, _label in bank_choices}
        self.fields["bank"].choices = [*bank_choices, ("physical", "Pago físico")]
        self.fields["payment_method"].choices = self.METHOD_CHOICES
        self.apply_styles()

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("payment_method")
        bank = cleaned.get("bank")
        receipt = cleaned.get("receipt")

        if method == "cash":
            cleaned["bank"] = "physical"
        else:
            if bank == "physical":
                self.add_error("bank", "Selecciona una cuenta bancaria para una transferencia o depósito.")
            elif bank and bank not in self.available_bank_codes:
                self.add_error("bank", "La cuenta seleccionada ya no está disponible.")
            if not receipt:
                self.add_error("receipt", "Sube el comprobante de la transferencia o depósito.")
        return cleaned

    def clean_period(self):
        value = self.cleaned_data["period"]
        return value.replace(day=1)


class DriverBlockForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(
        label="Motivo del bloqueo",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ej.: Mensualidad pendiente de agosto de 2026."}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class PaymentBankAccountForm(StyledFormMixin, forms.ModelForm):
    logo_file = forms.ImageField(
        label="Logo del banco (opcional)",
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    qr_file = forms.ImageField(
        label="Código QR (opcional)",
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )

    class Meta:
        model = PaymentBankAccount
        fields = [
            "code",
            "account_holder",
            "account_number",
            "account_type",
            "identification_number",
            "instructions",
            "is_active",
            "sort_order",
        ]
        labels = {
            "code": "Banco",
            "account_holder": "Titular de la cuenta",
            "account_number": "Número de cuenta",
            "account_type": "Tipo de cuenta",
            "identification_number": "Cédula o RUC del titular",
            "instructions": "Indicaciones para el transportista",
            "is_active": "Mostrar este banco",
            "sort_order": "Orden",
        }
        widgets = {
            "code": forms.Select(choices=PaymentBankAccount.BANK_CHOICES),
            "account_holder": forms.TextInput(attrs={"maxlength": 160, "placeholder": "Ej. MOVIX Loja"}),
            "account_number": forms.TextInput(attrs={"maxlength": 80, "placeholder": "Ej. 2200123456"}),
            "account_type": forms.Select(choices=PaymentBankAccount.ACCOUNT_TYPE_CHOICES),
            "identification_number": forms.TextInput(attrs={"maxlength": 20, "placeholder": "Cédula o RUC"}),
            "instructions": forms.Textarea(attrs={"rows": 3, "maxlength": 600, "placeholder": "Indicaciones opcionales para realizar la transferencia"}),
            "sort_order": forms.NumberInput(attrs={"min": 0, "max": 99}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class DriverInboxMessageForm(StyledFormMixin, forms.ModelForm):
    send_email = forms.BooleanField(
        label="Enviar también al correo del transportista",
        required=False,
        initial=True,
    )
    meeting_at = forms.DateTimeField(
        label="Fecha y hora de la reunión (opcional)",
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = DriverInboxMessage
        fields = ["driver", "message_type", "title", "body"]
        labels = {
            "driver": "Transportista",
            "message_type": "Tipo de mensaje",
            "title": "Título",
            "body": "Mensaje",
        }
        widgets = {
            "message_type": forms.Select(),
            "title": forms.TextInput(attrs={"maxlength": 180, "placeholder": "Ej. Reunión mensual de transportistas"}),
            "body": forms.Textarea(attrs={"rows": 5, "maxlength": 3000, "placeholder": "Escribe un mensaje claro para el transportista..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["driver"].queryset = Profile.objects.filter(
            role__in=["driver", "conductor", "transportista"]
        ).order_by("first_name", "last_name")
        self.fields["message_type"].choices = [
            choice for choice in DriverInboxMessage.TYPE_CHOICES if choice[0] != "invoice"
        ]
        self.apply_styles()


class SupabasePasswordChangeForm(StyledFormMixin, forms.Form):
    new_password = forms.CharField(
        label="Nueva contraseña",
        min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Las contraseñas no coinciden.")
        return cleaned


class NotificationForm(StyledFormMixin, forms.Form):
    AUDIENCES = [
        ("all", "Todos los usuarios"),
        ("clients", "Todos los clientes"),
        ("drivers", "Todos los transportistas"),
        ("specific", "Un usuario específico"),
    ]
    audience = forms.ChoiceField(label="Enviar a", choices=AUDIENCES)
    recipient = forms.ModelChoiceField(label="Buscar usuario", queryset=Profile.objects.none(), required=False)
    title = forms.CharField(label="Título", max_length=120)
    message = forms.CharField(label="Mensaje", max_length=500, widget=forms.Textarea(attrs={"rows": 7}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipient"].queryset = Profile.objects.filter(is_active=True).order_by("first_name", "last_name")
        self.apply_styles()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("audience") == "specific" and not cleaned.get("recipient"):
            self.add_error("recipient", "Selecciona el destinatario.")
        return cleaned


class AdvertisementForm(StyledFormMixin, forms.ModelForm):
    image = forms.ImageField(label="Banner publicitario", required=True)

    class Meta:
        model = Advertisement
        fields = ["title", "description", "target_url", "audience", "starts_at", "ends_at", "is_active"]
        labels = {
            "title": "Título",
            "description": "Descripción",
            "target_url": "Enlace al tocar el banner",
            "audience": "Mostrar a",
            "starts_at": "Fecha de inicio",
            "ends_at": "Fecha de finalización",
            "is_active": "Banner activo",
        }
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "audience": forms.Select(choices=[("all", "Todos"), ("clients", "Clientes"), ("drivers", "Transportistas")]),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class AdminProfileForm(StyledFormMixin, forms.Form):
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellido", max_length=150, required=False)
    email = forms.EmailField(label="Correo electrónico")
    phone = forms.CharField(label="Teléfono", max_length=30, required=False)
    city = forms.CharField(label="Ciudad", max_length=120, required=False)
    avatar = forms.ImageField(label="Foto de perfil", required=False)
    cover = forms.ImageField(label="Imagen de portada", required=False)

    def __init__(self, *args, user: User, **kwargs):
        self.user = user
        profile, _ = AdminProfile.objects.get_or_create(user=user)
        self.admin_profile = profile
        kwargs.setdefault(
            "initial",
            {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": profile.phone,
                "city": profile.city,
            },
        )
        super().__init__(*args, **kwargs)
        self.apply_styles()


class SettingsForm(StyledFormMixin, forms.Form):
    app_name = forms.CharField(label="Nombre de la aplicación", max_length=80, initial="MOVIX")
    support_email = forms.EmailField(label="Correo de soporte", required=False)
    max_upload_mb = forms.IntegerField(label="Tamaño máximo de archivos (MB)", min_value=1, max_value=50, initial=10)
    notifications_enabled = forms.BooleanField(label="Permitir notificaciones", required=False, initial=True)
    maintenance_mode = forms.BooleanField(label="Modo mantenimiento", required=False)
    dark_mode = forms.BooleanField(label="Usar modo oscuro en este navegador", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class PublicContactForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput, label="")
    privacy_accepted = forms.BooleanField(
        required=True,
        label="Acepto que MOVIX utilice estos datos para responder mi solicitud.",
    )

    class Meta:
        model = ContactRequest
        fields = ["full_name", "email", "phone", "request_type", "subject", "message"]
        labels = {
            "full_name": "Nombre completo",
            "email": "Correo electrónico",
            "phone": "Teléfono",
            "request_type": "¿Cómo podemos ayudarte?",
            "subject": "Asunto",
            "message": "Cuéntanos lo que necesitas",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "Ej. María González", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"placeholder": "nombre@correo.com", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"placeholder": "+593 99 000 0000", "autocomplete": "tel", "inputmode": "tel"}),
            "request_type": forms.Select(),
            "subject": forms.TextInput(attrs={"placeholder": "¿En qué podemos ayudarte?"}),
            "message": forms.Textarea(attrs={"rows": 5, "placeholder": "Escribe los detalles de tu consulta...", "maxlength": 2000}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.setdefault("class", "landing-input")
        self.fields["privacy_accepted"].widget.attrs["class"] = "landing-checkbox"

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("No se pudo procesar la solicitud.")
        return value


class ContactResponseForm(forms.ModelForm):
    class Meta:
        model = ContactRequest
        fields = ["admin_response"]
        labels = {"admin_response": "Respuesta del administrador"}
        widgets = {
            "admin_response": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 8,
                    "placeholder": "Escribe la respuesta para esta solicitud...",
                    "maxlength": 4000,
                }
            )
        }

    def clean_admin_response(self):
        value = (self.cleaned_data.get("admin_response") or "").strip()
        if not value:
            raise forms.ValidationError("Escribe una respuesta antes de guardarla.")
        return value
