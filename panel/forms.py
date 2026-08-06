from django import forms
from django.contrib.auth.models import User

from .models import AdminProfile, Advertisement, Profile


INPUT_CLASS = "form-control"


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
            "vehicle_type": forms.TextInput(attrs={"maxlength": 80}),
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
        self.apply_styles()

    def clean_identification_number(self):
        value = (self.cleaned_data.get("identification_number") or "").strip()
        if value and (not value.isdigit() or len(value) != 10):
            raise forms.ValidationError("La cédula debe contener exactamente 10 dígitos.")
        return value or None


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
