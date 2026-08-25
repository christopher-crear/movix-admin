import re
from datetime import date

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import (
    AdminProfile,
    Advertisement,
    ContactRequest,
    DriverInboxMessage,
    DriverMonthlyPayment,
    FleetDriver,
    FleetVehicle,
    PaymentBankAccount,
    Profile,
)


INPUT_CLASS = "form-control"

VEHICLE_TYPE_CHOICES = [
    ("camioneta", "Camioneta"),
    ("camion_pequeno", "Camión pequeño"),
    ("camion_mediano", "Camión mediano"),
]

NAME_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:[ '\-][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*$")


def validate_ecuador_identification(value, label="La cédula"):
    value = re.sub(r"\D", "", value or "")
    if len(value) != 10:
        raise forms.ValidationError(f"{label} debe contener exactamente 10 dígitos.")
    province, third = int(value[:2]), int(value[2])
    if province not in {*range(1, 25), 30} or third >= 6:
        raise forms.ValidationError(f"{label} no tiene un formato ecuatoriano válido.")
    total = 0
    for index, digit in enumerate(map(int, value[:9])):
        product = digit * (2 if index % 2 == 0 else 1)
        total += product - 9 if product > 9 else product
    if (10 - total % 10) % 10 != int(value[-1]):
        raise forms.ValidationError(f"{label} no supera la validación ecuatoriana.")
    return value


def validate_name(value, label="Este campo"):
    value = " ".join((value or "").strip().split())
    if value and not NAME_RE.fullmatch(value):
        raise forms.ValidationError(f"{label} solo admite letras, espacios, apóstrofes y guiones.")
    return value


def validate_ecuador_phone(value):
    value = re.sub(r"[\s()-]", "", value or "")
    if value.startswith("+593"):
        value = "0" + value[4:]
    if not re.fullmatch(r"09\d{8}", value):
        raise forms.ValidationError("Ingresa un celular ecuatoriano de 10 dígitos que empiece con 09.")
    return value


def validate_ecuador_plate(value):
    compact = re.sub(r"[\s-]", "", value or "").upper()
    if not re.fullmatch(r"[A-Z]{3}\d{3,4}", compact):
        raise forms.ValidationError("La placa debe tener el formato ecuatoriano ABC-123 o ABC-1234.")
    return f"{compact[:3]}-{compact[3:]}"


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
            "permit_number",
            "permit_details",
            "company_name",
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
            "permit_number": "Número de permiso de operación",
            "permit_details": "Datos adicionales del permiso",
            "company_name": "Compañía para la que trabaja",
            "is_available": "Disponible para servicios",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"maxlength": 80, "autocomplete": "given-name", "data-letters-only": "true"}),
            "last_name": forms.TextInput(attrs={"maxlength": 80, "autocomplete": "family-name", "data-letters-only": "true"}),
            "email": forms.EmailInput(attrs={"maxlength": 160, "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"maxlength": 10, "inputmode": "numeric", "autocomplete": "tel", "data-digits-only": "true", "placeholder": "09XXXXXXXX"}),
            "identification_number": forms.TextInput(attrs={"maxlength": 10, "inputmode": "numeric", "data-digits-only": "true"}),
            "license_number": forms.TextInput(attrs={"maxlength": 10, "inputmode": "numeric", "data-digits-only": "true"}),
            "vehicle_plate": forms.TextInput(attrs={"maxlength": 8, "data-ecuador-plate": "true", "placeholder": "ABC-1234"}),
            "load_capacity": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "vehicle_year": forms.NumberInput(attrs={"min": 1950, "max": 2100, "inputmode": "numeric"}),
            "vehicle_type": forms.Select(choices=VEHICLE_TYPE_CHOICES),
            "experience_years": forms.NumberInput(attrs={"min": 0, "max": 80, "inputmode": "numeric"}),
            "permit_number": forms.TextInput(attrs={"maxlength": 40, "data-code-only": "true"}),
            "permit_details": forms.TextInput(attrs={"maxlength": 250}),
            "company_name": forms.TextInput(attrs={"maxlength": 160, "data-business-name": "true"}),
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
                "permit_number",
                "permit_details",
                "company_name",
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
        return validate_ecuador_identification(value) if value else None

    def clean_first_name(self):
        return validate_name(self.cleaned_data.get("first_name"), "El nombre")

    def clean_last_name(self):
        return validate_name(self.cleaned_data.get("last_name"), "El apellido")

    def clean_phone(self):
        value = (self.cleaned_data.get("phone") or "").strip()
        return validate_ecuador_phone(value) if value else None

    def clean_license_number(self):
        value = (self.cleaned_data.get("license_number") or "").strip()
        return validate_ecuador_identification(value, "El número de licencia") if value else None

    def clean_vehicle_plate(self):
        value = (self.cleaned_data.get("vehicle_plate") or "").strip()
        return validate_ecuador_plate(value) if value else None

    def clean_vehicle_year(self):
        value = self.cleaned_data.get("vehicle_year")
        if value and not date.today().year - 15 <= value <= date.today().year:
            raise forms.ValidationError(f"El vehículo debe ser de {date.today().year - 15} a {date.today().year}.")
        return value

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


class PublicDriverRegistrationForm(ProfileCreateForm):
    """Registro público completo; siempre crea un transportista pendiente."""

    accept_terms = forms.BooleanField(
        label="Acepto los términos y condiciones y la política de tratamiento de datos",
        error_messages={"required": "Debes aceptar los términos y condiciones para registrarte."},
    )

    def __init__(self, *args, **kwargs):
        self.google_registration = bool(kwargs.pop("google_registration", False))
        self.google_avatar_url = (kwargs.pop("google_avatar_url", "") or "").strip()
        kwargs.pop("role", None)
        super().__init__(*args, role="transportista", **kwargs)
        self.fields["password"].label = "Contraseña"
        self.fields["password_confirm"].label = "Repite la contraseña"
        self.fields["experience_years"].required = True
        for name in (
            "identification_file", "vehicle_file", "license_file",
            "registration_file", "insurance_file",
        ):
            self.fields[name].required = True
        # Google entrega una fotografía únicamente cuando la cuenta posee una.
        # En ese caso se usa como avatar y no se vuelve a exigir otra carga.
        self.fields["profile_file"].required = not bool(self.google_avatar_url)
        if self.google_registration:
            self.fields["email"].disabled = True
            self.fields["password"].required = False
            self.fields["password_confirm"].required = False
            self.fields["password"].widget = forms.HiddenInput()
            self.fields["password_confirm"].widget = forms.HiddenInput()
        self.fields["profile_file"].help_text = (
            "Foto reciente tipo carnet: de frente, rostro visible, fondo claro, sin filtros, gorra ni gafas oscuras."
        )
        self.fields["vehicle_file"].help_text = "Fotografía completa y nítida del vehículo; la placa debe ser visible."
        self.fields["identification_file"].help_text = "Cédula completa, vigente, legible y sin reflejos. JPG, PNG, WEBP o PDF."
        self.fields["license_file"].help_text = "Licencia de conducir completa, vigente y legible."
        self.fields["registration_file"].help_text = "Matrícula vehicular completa y vigente."
        self.fields["insurance_file"].help_text = "Documento vigente del seguro vehicular."
        self.order_fields([
            "first_name", "last_name", "email", "phone", "identification_number",
            "license_number", "vehicle_plate", "load_capacity", "vehicle_year",
            "vehicle_type", "experience_years", "profile_file", "identification_file",
            "vehicle_file", "license_file", "registration_file", "insurance_file",
            "password", "password_confirm", "accept_terms",
        ])

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()
        if self.google_registration:
            # ProfileCreateForm compara ambos valores. Los dejamos vacíos
            # porque la identidad ya fue validada por Google/Supabase.
            cleaned["password"] = ""
            cleaned["password_confirm"] = ""
        password = cleaned.get("password")
        if password:
            try:
                password_validation.validate_password(password)
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class PasswordRecoveryRequestForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(
        label="Correo de tu cuenta MOVIX",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "correo@gmail.com"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class PasswordResetConfirmForm(StyledFormMixin, forms.Form):
    new_password = forms.CharField(
        label="Nueva contraseña",
        min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        label="Repite la nueva contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("new_password")
        if password and password != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Las contraseñas no coinciden.")
        if password:
            try:
                password_validation.validate_password(password)
            except ValidationError as exc:
                self.add_error("new_password", exc)
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


class FleetVehicleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FleetVehicle
        fields = ["alias", "plate", "vehicle_type", "year", "load_capacity", "permit_number", "is_active"]
        labels = {
            "alias": "Nombre para identificarlo",
            "plate": "Placa",
            "vehicle_type": "Tipo de vehículo",
            "year": "Año",
            "load_capacity": "Capacidad (kg)",
            "permit_number": "Permiso de operación",
            "is_active": "Vehículo activo",
        }
        widgets = {
            "alias": forms.TextInput(attrs={"maxlength": 80}),
            "plate": forms.TextInput(attrs={"maxlength": 8, "data-ecuador-plate": "true", "placeholder": "ABC-1234"}),
            "vehicle_type": forms.Select(choices=VEHICLE_TYPE_CHOICES),
            "year": forms.NumberInput(attrs={"min": date.today().year - 15, "max": date.today().year, "inputmode": "numeric"}),
            "load_capacity": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "permit_number": forms.TextInput(attrs={"maxlength": 40, "data-code-only": "true"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()

    def clean_plate(self):
        return validate_ecuador_plate(self.cleaned_data.get("plate"))

    def clean_year(self):
        value = self.cleaned_data.get("year")
        if value and not date.today().year - 15 <= value <= date.today().year:
            raise forms.ValidationError(f"El vehículo debe ser de {date.today().year - 15} a {date.today().year}.")
        return value


class FleetDriverForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FleetDriver
        fields = ["first_name", "last_name", "identification_number", "license_number", "phone", "email", "vehicle", "is_active"]
        labels = {
            "first_name": "Nombres", "last_name": "Apellidos", "identification_number": "Cédula",
            "license_number": "Licencia", "phone": "Teléfono", "email": "Correo",
            "vehicle": "Vehículo asignado", "is_active": "Chofer activo",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"maxlength": 80, "data-letters-only": "true"}),
            "last_name": forms.TextInput(attrs={"maxlength": 80, "data-letters-only": "true"}),
            "identification_number": forms.TextInput(attrs={"maxlength": 10, "inputmode": "numeric", "data-digits-only": "true"}),
            "license_number": forms.TextInput(attrs={"maxlength": 10, "inputmode": "numeric", "data-digits-only": "true"}),
            "phone": forms.TextInput(attrs={"maxlength": 10, "inputmode": "numeric", "data-digits-only": "true", "placeholder": "09XXXXXXXX"}),
            "email": forms.EmailInput(attrs={"maxlength": 160}),
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner:
            self.fields["vehicle"].queryset = FleetVehicle.objects.filter(owner=owner, is_active=True)
        self.apply_styles()

    def clean_identification_number(self):
        return validate_ecuador_identification(self.cleaned_data.get("identification_number"))

    def clean_first_name(self):
        return validate_name(self.cleaned_data.get("first_name"), "El nombre")

    def clean_last_name(self):
        return validate_name(self.cleaned_data.get("last_name"), "El apellido")

    def clean_license_number(self):
        return validate_ecuador_identification(self.cleaned_data.get("license_number"), "El número de licencia")

    def clean_phone(self):
        value = (self.cleaned_data.get("phone") or "").strip()
        return validate_ecuador_phone(value) if value else None


class AdminFleetVehicleForm(FleetVehicleForm):
    owner = forms.ModelChoiceField(label="Propietario transportista", queryset=Profile.objects.none())

    def __init__(self, *args, owners=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = owners if owners is not None else Profile.objects.none()
        self.order_fields(["owner", *self.Meta.fields])


class AdminFleetDriverForm(FleetDriverForm):
    owner = forms.ModelChoiceField(label="Propietario transportista", queryset=Profile.objects.none())

    def __init__(self, *args, owners=None, **kwargs):
        owner = kwargs.pop("owner", None)
        super().__init__(*args, owner=owner, **kwargs)
        self.fields["owner"].queryset = owners if owners is not None else Profile.objects.none()
        if self.is_bound and not owner:
            owner_id = self.data.get("owner")
            self.fields["vehicle"].queryset = FleetVehicle.objects.filter(owner_id=owner_id, is_active=True)
        elif not self.is_bound:
            self.fields["vehicle"].queryset = FleetVehicle.objects.filter(is_active=True).select_related("owner")
        self.fields["vehicle"].label_from_instance = lambda item: f"{item.owner.full_name} · {item.plate} · {item.alias or item.vehicle_type}"
        self.order_fields(["owner", *self.Meta.fields])

    def clean(self):
        cleaned = super().clean()
        owner, vehicle = cleaned.get("owner"), cleaned.get("vehicle")
        if owner and vehicle and vehicle.owner_id != owner.id:
            self.add_error("vehicle", "El vehículo debe pertenecer al propietario seleccionado.")
        return cleaned


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
        fields = ["vehicle", "period", "amount", "bank", "payment_method"]
        labels = {
            "vehicle": "Vehículo que cubre la mensualidad",
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

    def __init__(self, *args, bank_accounts=None, driver=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicle"].queryset = FleetVehicle.objects.filter(owner=driver, is_active=True) if driver else FleetVehicle.objects.none()
        self.fields["vehicle"].label_from_instance = lambda item: f"{item.plate} · {item.alias or item.vehicle_type}"
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
