import uuid
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django import forms
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, SimpleTestCase, TransactionTestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import (
    DriverSelfProfileForm,
    PasswordRecoveryRequestForm,
    PasswordResetConfirmForm,
    ProfileCreateForm,
    ProfileForm,
    PublicContactForm,
    PublicDriverRegistrationForm,
)
from .models import (
    Advertisement,
    AdminNotification,
    AdminProfile,
    AuditLog,
    ContactRequest,
    DeviceToken,
    DriverMonthlyPayment,
    DriverInboxMessage,
    DriverInvoice,
    DriverReview,
    FleetDriver,
    FleetVehicle,
    Notification,
    NotificationCampaign,
    PaymentBankAccount,
    Profile,
    Ride,
    RideStop,
    SystemSetting,
)
from .services import is_safe_media_url, resolve_media_url, send_movix_email, upload_to_supabase


EXTERNAL_MODELS = [
    Profile,
    Ride,
    RideStop,
    FleetVehicle,
    FleetDriver,
    DriverReview,
    Notification,
    DriverMonthlyPayment,
    PaymentBankAccount,
    DriverInvoice,
    DriverInboxMessage,
    Advertisement,
    NotificationCampaign,
    DeviceToken,
    AuditLog,
    SystemSetting,
    AdminNotification,
]


class PublicPagesTests(SimpleTestCase):
    def test_landing_page_renders(self):
        response = self.client.get(reverse("panel:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Transporte de carga en Loja")
        self.assertContains(response, "data-floating-phone")

    def test_public_demo_renders_without_authentication(self):
        response = self.client.get(reverse("panel:demo"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Continuar con Google")
        self.assertContains(response, "Continuar con Facebook")
        self.assertContains(response, "data-demo-panel=\"home\"")
        self.assertContains(response, "data-demo-panel=\"payment\"")
        self.assertContains(response, "Datos 100% ficticios")
        self.assertNotContains(response, "Christopher Eras")

    def test_landing_exposes_driver_portal_without_naming_admin_panel(self):
        response = self.client.get(reverse("panel:landing"))
        self.assertContains(response, reverse("login"))
        self.assertContains(response, "Portal transportista")
        self.assertContains(response, "Ingresar como transportista")
        self.assertContains(response, "img/landing/pantalla-movix.png")
        self.assertContains(response, "img/landing/camioneta.jpeg")
        self.assertContains(response, "img/landing/camion-pequeno.jpg")
        self.assertContains(response, "img/landing/camion-mediano.jpg")
        self.assertNotContains(response, reverse("panel:demo"))
        self.assertNotContains(response, "Prueba demo")
        self.assertNotContains(response, "Panel administrativo")
        self.assertContains(response, "eraschristopher0@gmail.com")
        self.assertContains(response, "593989414258")

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bienvenido a MOVIX")
        self.assertContains(response, "Continuar con Google")
        self.assertContains(response, reverse("driver_registration"))
        self.assertContains(response, reverse("password_recovery"))

    def test_public_driver_registration_renders_document_guidance(self):
        response = self.client.get(reverse("driver_registration"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Foto de perfil tipo carnet")
        self.assertContains(response, "Cédula completa")
        self.assertContains(response, "Matrícula vehicular")
        self.assertContains(response, "términos y condiciones")

    def test_google_registration_uses_avatar_and_does_not_require_profile_upload_or_password(self):
        form = PublicDriverRegistrationForm(
            google_registration=True,
            google_avatar_url="https://lh3.googleusercontent.com/photo.jpg",
            initial={"email": "google@example.com"},
        )
        self.assertFalse(form.fields["profile_file"].required)
        self.assertFalse(form.fields["password"].required)
        self.assertTrue(form.fields["email"].disabled)

    def test_google_without_avatar_still_requires_profile_upload(self):
        form = PublicDriverRegistrationForm(google_registration=True, google_avatar_url="")
        self.assertTrue(form.fields["profile_file"].required)

    def test_password_recovery_and_terms_pages_are_public(self):
        recovery = self.client.get(reverse("password_recovery"))
        terms = self.client.get(reverse("terms_and_conditions"))
        self.assertEqual(recovery.status_code, 200)
        self.assertEqual(terms.status_code, 200)
        self.assertContains(recovery, "Recupera tu contraseña")
        self.assertContains(terms, "Documento de prueba")

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(reverse("panel:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class BrevoEmailTests(SimpleTestCase):
    @override_settings(
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_API_URL="https://api.brevo.com/v3/smtp/email",
        BREVO_SENDER_EMAIL="movix_soporte@gmail.com",
        BREVO_SENDER_NAME="MOVIX",
    )
    @patch("panel.services.requests.post")
    def test_brevo_sends_pdf_attachment_over_https(self, post):
        post.return_value = Mock(status_code=201)

        sent, error = send_movix_email(
            "transportista@example.com", "Factura MOVIX",
            "Adjuntamos tu factura.", "FACT-001.pdf", b"%PDF-1.4 prueba",
        )

        self.assertTrue(sent)
        self.assertEqual(error, "")
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["api-key"], "brevo-test-key")
        self.assertEqual(kwargs["json"]["to"], [{"email": "transportista@example.com"}])
        self.assertEqual(kwargs["json"]["attachment"][0]["name"], "FACT-001.pdf")
        self.assertTrue(kwargs["json"]["attachment"][0]["content"])

    @override_settings(
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_API_URL="https://api.brevo.com/v3/smtp/email",
        BREVO_SENDER_EMAIL="movix_soporte@gmail.com",
        BREVO_SENDER_NAME="MOVIX",
    )
    @patch("panel.services.requests.post")
    def test_brevo_returns_readable_api_error(self, post):
        post.return_value = Mock(status_code=400)
        post.return_value.json.return_value = {"message": "sender not valid"}

        sent, error = send_movix_email("destino@example.com", "Aviso", "Prueba")

        self.assertFalse(sent)
        self.assertIn("Brevo respondió 400", error)
        self.assertIn("sender not valid", error)


class FormTests(SimpleTestCase):
    def test_public_driver_registration_requires_all_documents_and_terms(self):
        form = PublicDriverRegistrationForm()
        for field_name in (
            "profile_file", "identification_file", "vehicle_file", "license_file",
            "registration_file", "insurance_file", "accept_terms",
        ):
            self.assertTrue(form.fields[field_name].required)
        self.assertIn("tipo carnet", form.fields["profile_file"].help_text)

    def test_password_recovery_forms_have_expected_fields(self):
        self.assertEqual(list(PasswordRecoveryRequestForm().fields), ["email"])
        self.assertEqual(
            list(PasswordResetConfirmForm().fields),
            ["new_password", "confirm_password"],
        )

    def test_public_contact_form_uses_compact_fields(self):
        form = PublicContactForm()
        self.assertIsInstance(form.fields["full_name"].widget, forms.TextInput)
        self.assertIsInstance(form.fields["email"].widget, forms.EmailInput)
        self.assertIsInstance(form.fields["message"].widget, forms.Textarea)

    def test_profile_text_fields_render_as_compact_inputs(self):
        form = ProfileForm(role="cliente")
        self.assertIsInstance(form.fields["first_name"].widget, forms.TextInput)
        self.assertNotIsInstance(form.fields["first_name"].widget, forms.Textarea)
        self.assertIsInstance(form.fields["email"].widget, forms.EmailInput)

    def test_only_admin_profile_form_exposes_fleet_assignment(self):
        admin_form = ProfileCreateForm(role="transportista", allow_fleet_assignment=True)
        public_form = PublicDriverRegistrationForm()
        self.assertIn("is_fleet_owner", admin_form.fields)
        self.assertIn("fleet_owner", admin_form.fields)
        self.assertNotIn("is_fleet_owner", public_form.fields)
        self.assertNotIn("fleet_owner", public_form.fields)
        self.assertIn("permit_file", public_form.fields)

    def test_ecuador_plate_is_normalized_and_invalid_phone_is_rejected(self):
        form = ProfileForm(
            data={
                "first_name": "María", "last_name": "Vera", "email": "maria@example.com",
                "phone": "09999ABC99", "identification_number": "1106056011",
                "license_number": "1106056011", "vehicle_plate": "laa5986",
                "load_capacity": "900", "vehicle_year": str(timezone.localdate().year),
                "vehicle_type": "camioneta", "experience_years": "5", "is_available": "on",
            },
            role="transportista",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)
        self.assertEqual(form.cleaned_data["vehicle_plate"], "LAA-5986")

    def test_ecuador_phone_is_saved_with_international_prefix(self):
        form = ProfileForm(
            data={
                "first_name": "María", "last_name": "Vera", "email": "maria@example.com",
                "phone": "987654321", "identification_number": "1106056011",
                "license_number": "1106056011", "vehicle_plate": "LAA-5986",
                "load_capacity": "900", "vehicle_year": str(timezone.localdate().year),
                "vehicle_type": "camioneta", "experience_years": "5", "is_available": "on",
            },
            role="transportista",
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "+593987654321")

    def test_names_reject_numbers_and_license_requires_ecuadorian_number(self):
        form = ProfileForm(
            data={
                "first_name": "María2", "last_name": "Vera", "email": "maria@example.com",
                "phone": "0999999999", "identification_number": "1106056011",
                "license_number": "LIC-123", "vehicle_plate": "LAA-5986",
                "load_capacity": "900", "vehicle_year": str(timezone.localdate().year),
                "vehicle_type": "camioneta", "experience_years": "5", "is_available": "on",
            },
            role="transportista",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)
        self.assertIn("license_number", form.errors)

    def test_driver_vehicle_type_is_limited_to_three_choices(self):
        form = ProfileForm(role="transportista")
        self.assertIsInstance(form.fields["vehicle_type"].widget, forms.Select)
        self.assertEqual(
            list(form.fields["vehicle_type"].widget.choices),
            [("camioneta", "Camioneta"), ("camion_pequeno", "Camión pequeño"), ("camion_mediano", "Camión mediano")],
        )

    def test_driver_can_upload_identification_document_from_own_profile(self):
        form = DriverSelfProfileForm(role="transportista")
        self.assertIn("identification_file", form.fields)
        self.assertNotIn("identification_number", form.fields)
        self.assertNotIn("email", form.fields)

    def test_invalid_ecuadorian_identification_length(self):
        form = ProfileCreateForm(
            data={
                "first_name": "María",
                "last_name": "Vera",
                "email": "maria@example.com",
                "phone": "0999999999",
                "identification_number": "123",
                "password": "ClaveSegura123",
                "password_confirm": "ClaveSegura123",
            },
            role="cliente",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("identification_number", form.errors)

    def test_password_confirmation(self):
        form = ProfileCreateForm(
            data={
                "first_name": "María",
                "last_name": "Vera",
                "email": "maria@example.com",
                "phone": "0999999999",
                "identification_number": "1106056011",
                "password": "ClaveSegura123",
                "password_confirm": "OtraClave123",
            },
            role="cliente",
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password_confirm", form.errors)


@override_settings(
    SUPABASE_URL="https://project.supabase.co",
    SUPABASE_SERVICE_ROLE_KEY="sb_secret_test",
    SUPABASE_PUBLIC_BUCKET="movix-public",
    SUPABASE_PRIVATE_BUCKET="movix-documents",
    MAX_UPLOAD_MB=10,
)
class StorageServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("panel.services.requests.post")
    @patch("panel.services.requests.get")
    def test_public_image_upload_returns_public_url(self, get_mock, post_mock):
        get_mock.return_value = Mock(status_code=200)
        post_mock.return_value = Mock(status_code=200)
        image = SimpleUploadedFile("perfil.png", b"imagen", content_type="image/png")
        value = upload_to_supabase(image, "profiles/demo/profile", public=True, images_only=True)
        self.assertTrue(value.startswith("https://project.supabase.co/storage/v1/object/public/movix-public/"))
        self.assertEqual(post_mock.call_count, 1)

    @patch("panel.services._find_storage_objects", return_value=[("app-documents", "cedulas/usuario/cedula.jpg")])
    @patch("panel.services.requests.post")
    def test_raw_mobile_path_is_found_and_signed(self, post_mock, _lookup):
        response = Mock(status_code=200)
        response.json.return_value = {
            "signedURL": "/object/sign/app-documents/cedulas/usuario/cedula.jpg?token=nuevo"
        }
        post_mock.return_value = response
        url = resolve_media_url("cedulas/usuario/cedula.jpg", preferred_buckets=("movix-documents",))
        self.assertEqual(
            url,
            "https://project.supabase.co/storage/v1/object/sign/app-documents/cedulas/usuario/cedula.jpg?token=nuevo",
        )
        self.assertIn("/app-documents/cedulas/usuario/cedula.jpg", post_mock.call_args.args[0])

    @patch("panel.services.requests.post")
    def test_expired_signed_url_is_re_signed(self, post_mock):
        response = Mock(status_code=200)
        response.json.return_value = {
            "signedURL": "/object/sign/movix-documents/identification/demo.jpg?token=renovado"
        }
        post_mock.return_value = response
        old = "https://project.supabase.co/storage/v1/object/sign/movix-documents/identification/demo.jpg?token=vencido"
        self.assertIn("token=renovado", resolve_media_url(old))

    @patch(
        "panel.services._find_storage_objects",
        return_value=[("profile-media", "profiles/usuario/avatar.jpg", True)],
    )
    @patch("panel.services.requests.post")
    def test_historical_public_bucket_uses_public_url_without_signing(self, post_mock, _lookup):
        url = resolve_media_url("profiles/usuario/avatar.jpg")
        self.assertEqual(
            url,
            "https://project.supabase.co/storage/v1/object/public/profile-media/profiles/usuario/avatar.jpg",
        )
        post_mock.assert_not_called()

    def test_relative_storage_paths_are_safe_but_traversal_is_rejected(self):
        self.assertTrue(is_safe_media_url("identification/usuario/cedula.jpg"))
        self.assertTrue(is_safe_media_url("/storage/v1/object/public/movix-public/perfil.jpg"))
        self.assertFalse(is_safe_media_url("../../archivo.env"))
        self.assertFalse(is_safe_media_url("//sitio-malicioso.example/archivo.jpg"))


class PanelIntegrationTests(TransactionTestCase):
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as editor:
            for model in EXTERNAL_MODELS:
                editor.create_model(model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            for model in reversed(EXTERNAL_MODELS):
                editor.delete_model(model)
        super().tearDownClass()

    def setUp(self):
        for model in reversed(EXTERNAL_MODELS):
            model.objects.all().delete()
        ContactRequest.objects.all().delete()
        self.admin = User.objects.create_superuser("admin_movix", "admin@example.com", "PruebaSegura123")
        self.client.force_login(self.admin)
        self.user_profile = Profile.objects.create(
            id=uuid.uuid4(), role="cliente", first_name="María", last_name="González",
            email="maria@example.com", identification_number="1106056011", is_active=True,
            identification_photo_url="https://res.cloudinary.com/demo/image/upload/cedula.jpg",
            verification_status="pending", created_at=timezone.now(), updated_at=timezone.now(),
        )
        self.driver_profile = Profile.objects.create(
            id=uuid.uuid4(), role="transportista", first_name="Rafael", last_name="Eras",
            email="rafael@example.com", identification_number="1100000001", is_active=True,
            vehicle_plate="LAA-5986", verification_status="approved", profile_verified=True,
            created_at=timezone.now(), updated_at=timezone.now(),
        )
        self.bank_account = PaymentBankAccount.objects.create(
            code="banco_loja",
            account_holder="MOVIX Loja",
            account_number="2200123456",
            account_type="savings",
            identification_number="1100000000",
            is_active=True,
            sort_order=1,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

    def _open_driver_session(self):
        self.client.logout()
        session = self.client.session
        session["portal_profile_id"] = str(self.driver_profile.id)
        session["portal_role"] = "transportista"
        session.save()

    def _create_driver_ride(self, **overrides):
        values = {
            "client": self.user_profile,
            "driver": self.driver_profile,
            "origin_address": "Mercado Central, Loja",
            "destination_address": "Barrio Los Pinos, Loja",
            "price": Decimal("18.50"),
            "driver_price": Decimal("15.00"),
            "status": "completada",
            "distance_km": Decimal("7.25"),
            "created_at": timezone.now(),
            "completed_at": timezone.now(),
        }
        values.update(overrides)
        return Ride.objects.create(**values)

    def test_movix_rank_and_duration_format(self):
        self.driver_profile.rating = Decimal("4.80")
        self.driver_profile.completed_trips = 120
        self.assertEqual(self.driver_profile.movix_rank["label"], "Estrella MOVIX")
        ride = self._create_driver_ride(estimated_minutes=135)
        self.assertEqual(ride.estimated_duration_label, "2 h 15 min")

    def test_driver_sees_multipoint_route_earnings_and_fleet_modules(self):
        ride = self._create_driver_ride(
            estimated_minutes=75,
            route_stops=[
                {"type": "pickup", "address": "Bodega norte"},
                {"type": "delivery", "address": "Entrega centro"},
                {"type": "delivery", "address": "Entrega sur"},
            ],
        )
        RideStop.objects.create(id=uuid.uuid4(), ride=ride, stop_type="pickup", sequence=1, address="Bodega norte", created_at=timezone.now())
        RideStop.objects.create(id=uuid.uuid4(), ride=ride, stop_type="delivery", sequence=2, address="Entrega sur", created_at=timezone.now())
        self._open_driver_session()
        detail = self.client.get(reverse("panel:driver_ride_detail", args=[ride.id]))
        self.assertContains(detail, "Bodega norte")
        self.assertContains(detail, "Entrega centro")
        self.assertContains(detail, "1 h 15 min")
        rides = self.client.get(reverse("panel:driver_rides"))
        self.assertContains(rides, "Entrega centro")
        earnings = self.client.get(reverse("panel:driver_earnings"))
        self.assertEqual(earnings.status_code, 200)
        export = self.client.get(reverse("panel:driver_earnings"), {"export": "csv"})
        self.assertIn("Entrega 2", export.content.decode("utf-8-sig"))
        self.assertEqual(self.client.get(reverse("panel:driver_fleet")).status_code, 200)

    def test_fleet_owner_sees_real_driver_profiles_and_their_earnings(self):
        self.driver_profile.is_fleet_owner = True
        self.driver_profile.company_name = "Transportes Eras"
        self.driver_profile.save(update_fields=["is_fleet_owner", "company_name"])
        member = Profile.objects.create(
            id=uuid.uuid4(), role="transportista", first_name="Daniel", last_name="Vera",
            email="daniel.fleet@example.com", identification_number="1106056011",
            license_number="1106056011", vehicle_plate="LBA-1234", vehicle_type="camioneta",
            fleet_owner=self.driver_profile, is_active=True, created_at=timezone.now(), updated_at=timezone.now(),
        )
        ride = self._create_driver_ride(driver=member)
        self._open_driver_session()

        fleet = self.client.get(reverse("panel:driver_fleet"))
        self.assertContains(fleet, member.full_name)
        self.assertContains(fleet, member.vehicle_plate)
        earnings = self.client.get(reverse("panel:driver_earnings"))
        self.assertContains(earnings, member.full_name)
        self.assertContains(earnings, "15,00")
        self.assertEqual(self.client.get(reverse("panel:driver_ride_detail", args=[ride.id])).status_code, 200)

        self.client.force_login(self.admin)
        admin_fleet = self.client.get(reverse("panel:admin_fleet"))
        self.assertContains(admin_fleet, "Transportes Eras")
        self.assertContains(admin_fleet, member.full_name)

    @patch("panel.views.send_movix_email")
    def test_driver_password_recovery_sends_custom_movix_link(self, send_email):
        self.client.logout()
        response = self.client.post(
            reverse("password_recovery"),
            {"email": self.driver_profile.email},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Revisa tu correo")
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.args[0], self.driver_profile.email)
        self.assertIn("/recuperar-contrasena/", send_email.call_args.kwargs["action_url"])

    @patch("panel.views.supabase_admin_update_password")
    def test_driver_can_confirm_password_reset_for_supabase_auth(self, update_password):
        self.client.logout()
        token = signing.dumps(
            {
                "kind": "supabase",
                "id": str(self.driver_profile.id),
                "email": self.driver_profile.email,
                "nonce": uuid.uuid4().hex,
            },
            salt="movix-password-reset",
            compress=True,
        )
        response = self.client.post(
            reverse("password_reset_confirm", kwargs={"token": token}),
            {"new_password": "NuevaClaveMovix2026!", "confirm_password": "NuevaClaveMovix2026!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Contraseña actualizada")
        update_password.assert_called_once_with(self.driver_profile.id, "NuevaClaveMovix2026!")

    @patch("panel.views.supabase_password_sign_in")
    def test_driver_can_login_with_supabase_email_and_password(self, sign_in):
        self.client.logout()
        sign_in.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "user": {"id": str(self.driver_profile.id), "email": self.driver_profile.email},
        }

        response = self.client.post(
            reverse("login"),
            {"username": self.driver_profile.email, "password": "ClaveSegura123"},
        )

        self.assertRedirects(response, reverse("panel:driver_dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["portal_profile_id"], str(self.driver_profile.id))
        self.assertEqual(self.client.session["portal_role"], "transportista")
        sign_in.assert_called_once_with(self.driver_profile.email, "ClaveSegura123")

    def test_admin_can_login_normally_with_django_username_and_password(self):
        self.client.logout()

        response = self.client.post(
            reverse("login"),
            {"username": "admin_movix", "password": "PruebaSegura123"},
        )

        self.assertRedirects(response, reverse("panel:dashboard"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin.pk)

    def test_admin_username_rejects_an_incorrect_password(self):
        self.client.logout()

        response = self.client.post(
            reverse("login"),
            {"username": "admin_movix", "password": "ClaveIncorrecta"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usuario o contraseña incorrectos")
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("panel.views.supabase_password_sign_in")
    def test_driver_email_rejects_an_incorrect_password(self, sign_in):
        self.client.logout()
        sign_in.side_effect = ValidationError("Invalid login credentials")

        response = self.client.post(
            reverse("login"),
            {"username": self.driver_profile.email, "password": "ClaveIncorrecta"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Correo o contraseña incorrectos")
        self.assertNotIn("portal_profile_id", self.client.session)
        sign_in.assert_called_once_with(self.driver_profile.email, "ClaveIncorrecta")

    @patch("panel.views.supabase_password_sign_in")
    def test_driver_role_wins_when_email_is_also_used_by_django_staff(self, sign_in):
        self.client.logout()
        User.objects.create_user(
            username="admin_collision",
            email=self.driver_profile.email,
            password="ClaveSegura123",
            is_staff=True,
        )
        sign_in.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "user": {"id": str(self.driver_profile.id), "email": self.driver_profile.email},
        }

        response = self.client.post(
            reverse("login"),
            {"username": self.driver_profile.email, "password": "ClaveSegura123"},
        )

        self.assertRedirects(response, reverse("panel:driver_dashboard"), fetch_redirect_response=False)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(self.client.session["portal_role"], "transportista")

    @patch("panel.views.supabase_user_from_token")
    def test_google_driver_is_not_promoted_by_matching_staff_email(self, user_from_token):
        self.client.logout()
        User.objects.create_user(
            username="google_admin_collision",
            email=self.driver_profile.email,
            password="OtraClave123",
            is_staff=True,
        )
        user_from_token.return_value = {
            "id": str(self.driver_profile.id),
            "email": self.driver_profile.email,
        }

        response = self.client.post(
            reverse("panel:auth_session"),
            {"access_token": "google-token", "refresh_token": "refresh-token"},
        )

        self.assertRedirects(response, reverse("panel:driver_dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["portal_role"], "transportista")

    @patch("panel.views.supabase_user_from_token")
    def test_google_photo_is_copied_to_empty_driver_profile(self, user_from_token):
        self.client.logout()
        self.driver_profile.profile_photo_url = ""
        self.driver_profile.avatar_url = ""
        self.driver_profile.license_number = "LIC-TEST-2026"
        self.driver_profile.vehicle_type = "camioneta"
        self.driver_profile.save(update_fields=[
            "profile_photo_url", "avatar_url", "license_number", "vehicle_type",
        ])
        user_from_token.return_value = {
            "id": str(self.driver_profile.id),
            "email": self.driver_profile.email,
            "app_metadata": {"provider": "google"},
            "user_metadata": {"avatar_url": "https://lh3.googleusercontent.com/google-avatar.jpg"},
        }
        response = self.client.post(
            reverse("panel:auth_session"),
            {"access_token": "google-token", "refresh_token": "refresh-token"},
        )
        self.assertRedirects(response, reverse("panel:driver_dashboard"), fetch_redirect_response=False)
        self.driver_profile.refresh_from_db()
        self.assertEqual(self.driver_profile.profile_photo_url, "https://lh3.googleusercontent.com/google-avatar.jpg")

    def test_driver_portal_uses_real_supabase_models(self):
        ride = self._create_driver_ride()
        DriverReview.objects.create(
            ride=ride,
            client=self.user_profile,
            driver=self.driver_profile,
            rating=5,
            comment="Excelente atención y cuidado de la carga.",
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self._open_driver_session()

        dashboard = self.client.get(reverse("panel:driver_dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Mercado Central, Loja")
        self.assertContains(dashboard, 'class="app-shell"')
        self.assertContains(dashboard, "Mis carreras")
        self.assertNotContains(dashboard, 'class="driver-shell"')
        self.assertNotContains(dashboard, reverse("panel:profile_list", args=["users"]))
        self.assertEqual(dashboard.context["weekly_earnings"], ride.effective_price)

        rides = self.client.get(reverse("panel:driver_rides"))
        self.assertContains(rides, "Barrio Los Pinos, Loja")

        detail = self.client.get(reverse("panel:driver_ride_detail", args=[ride.id]))
        self.assertContains(detail, "Excelente atención y cuidado de la carga.")

        reviews = self.client.get(reverse("panel:driver_reviews"))
        self.assertContains(reviews, "Excelente atención y cuidado de la carga.")

        profile = self.client.get(reverse("panel:driver_profile"))
        self.assertContains(profile, self.driver_profile.full_name)
        self.assertContains(profile, self.driver_profile.vehicle_plate)
        self.assertContains(profile, "Editar información")
        self.assertContains(profile, "Mensualidad")

    @patch("panel.views.upload_to_supabase", return_value="storage://movix-documents/monthly-payments/demo/recibo.pdf")
    def test_driver_can_submit_monthly_payment_receipt(self, _upload):
        self._open_driver_session()
        receipt = SimpleUploadedFile("recibo.pdf", b"pdf-demo", content_type="application/pdf")
        response = self.client.post(
            reverse("panel:driver_payments"),
            {
                "period": timezone.localdate().strftime("%Y-%m"),
                "amount": "20.00",
                "bank": "banco_loja",
                "payment_method": "transfer",
                "receipt": receipt,
            },
        )
        self.assertEqual(response.status_code, 302)
        payment = DriverMonthlyPayment.objects.get(driver=self.driver_profile)
        self.assertEqual(payment.status, DriverMonthlyPayment.STATUS_PENDING)
        self.assertEqual(payment.bank, "banco_loja")
        self.assertTrue(payment.receipt_url.endswith("recibo.pdf"))

    @patch("panel.views.upload_to_supabase")
    def test_driver_can_register_physical_payment_without_receipt(self, upload):
        self._open_driver_session()
        response = self.client.post(
            reverse("panel:driver_payments"),
            {
                "period": timezone.localdate().strftime("%Y-%m"),
                "amount": "20.00",
                "bank": "physical",
                "payment_method": "cash",
            },
        )
        self.assertEqual(response.status_code, 302)
        upload.assert_not_called()
        payment = DriverMonthlyPayment.objects.get(driver=self.driver_profile)
        self.assertEqual(payment.bank, "physical")
        self.assertEqual(payment.payment_method, "cash")
        self.assertFalse(payment.receipt_url)

    def test_driver_sees_only_admin_configured_bank_and_mailbox(self):
        inbox_message = DriverInboxMessage.objects.create(
            driver=self.driver_profile,
            message_type="meeting",
            title="Reunión de transportistas",
            body="Nos reuniremos el viernes a las 18:00.",
            created_at=timezone.now(),
        )
        self._open_driver_session()

        payments = self.client.get(reverse("panel:driver_payments"))
        self.assertContains(payments, "Banco de Loja")
        self.assertContains(payments, "2200123456")
        self.assertContains(payments, 'data-bank-dialog-open=')
        self.assertContains(payments, '<option value="banco_loja"', html=False)
        self.assertContains(payments, '<option value="transfer"', html=False)
        self.assertContains(payments, '<option value="deposit"', html=False)
        self.assertContains(payments, '<option value="cash"', html=False)
        self.assertContains(payments, "Pago físico")

        inbox = self.client.get(reverse("panel:driver_inbox"))
        self.assertContains(inbox, "Reunión de transportistas")
        self.assertContains(inbox, "Sin leer")

        delete_response = self.client.post(reverse("panel:driver_inbox_delete", args=[inbox_message.id]))
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(DriverInboxMessage.objects.filter(pk=inbox_message.id).exists())

    @patch("panel.views.send_push_notifications", return_value=(0, ""))
    @patch("panel.views.active_tokens_for_users", return_value=[])
    def test_admin_can_block_driver_and_stores_notification_reason(self, _tokens, _push):
        response = self.client.post(
            reverse("panel:driver_payment_block", args=[self.driver_profile.id, "block"]),
            {"reason": "Mensualidad pendiente de agosto."},
        )
        self.assertEqual(response.status_code, 302)
        self.driver_profile.refresh_from_db()
        self.assertFalse(self.driver_profile.is_active)
        self.assertTrue(self.driver_profile.is_blocked)
        self.assertEqual(self.driver_profile.blocked_reason, "Mensualidad pendiente de agosto.")
        self.assertTrue(Notification.objects.filter(user=self.driver_profile, type="account_status", message__icontains="Mensualidad pendiente").exists())

    def test_admin_monthly_payment_module_lists_real_driver(self):
        payment = DriverMonthlyPayment.objects.create(
            driver=self.driver_profile,
            period=timezone.localdate().replace(day=1),
            amount=Decimal("18.00"), bank="jep", payment_method="deposit",
            receipt_url="storage://movix-documents/monthly-payments/receipt.jpg",
            status="pending", created_at=timezone.now(), updated_at=timezone.now(),
        )
        listing = self.client.get(reverse("panel:monthly_payment_list"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, self.driver_profile.full_name)
        self.assertContains(listing, "Cooperativa JEP")
        self.assertContains(listing, "payments-layout-v12")
        self.assertContains(listing, "payment-summary-grid")
        self.assertContains(listing, "payment-filter-toolbar")
        detail = self.client.get(reverse("panel:monthly_payment_detail", args=[payment.id]))
        self.assertContains(detail, "Comprobante adjunto")

        banks = self.client.get(reverse("panel:payment_bank_accounts"))
        self.assertContains(banks, "bank-admin-v12")
        self.assertContains(banks, "bank-settings-form")

        messages_view = self.client.get(reverse("panel:admin_driver_messages"))
        self.assertContains(messages_view, "message-center-v12")
        self.assertContains(messages_view, "message-history-panel")

    @patch("panel.views.send_push_notifications", return_value=(0, ""))
    @patch("panel.views.active_tokens_for_users", return_value=[])
    @patch("panel.views.send_movix_email", return_value=(True, ""))
    @patch("panel.views.upload_to_supabase", return_value="storage://movix-documents/monthly-invoices/fisico.pdf")
    @patch("panel.views.build_monthly_invoice_pdf", return_value=b"factura-fisica")
    def test_physical_payment_generates_invoice_automatically(
        self, _build, _upload, _email, _tokens, _push
    ):
        response = self.client.post(
            reverse("panel:monthly_payment_physical", args=[self.driver_profile.id]),
            {"period": "2026-08", "amount": "30.00"},
        )
        payment = DriverMonthlyPayment.objects.get(driver=self.driver_profile)
        invoice = DriverInvoice.objects.get(payment=payment)
        self.assertRedirects(
            response,
            reverse("panel:monthly_payment_detail", args=[payment.id]),
            fetch_redirect_response=False,
        )
        self.assertEqual(payment.payment_method, "cash")
        self.assertEqual(payment.amount, Decimal("30.00"))
        self.assertEqual(invoice.amount, Decimal("30.00"))
        self.assertTrue(
            DriverInboxMessage.objects.filter(invoice=invoice, driver=self.driver_profile).exists()
        )

    @patch("panel.views.send_push_notifications", return_value=(0, ""))
    @patch("panel.views.active_tokens_for_users", return_value=[])
    @patch("panel.views.send_movix_email", return_value=(True, ""))
    @patch("panel.views.upload_to_supabase", return_value="storage://movix-documents/monthly-invoices/factura.pdf")
    @patch("panel.views.build_monthly_invoice_pdf", return_value=b"factura-pdf")
    def test_admin_generates_invoice_for_approved_payment_and_driver_receives_it(
        self, _build, _upload, send_email, _tokens, _push
    ):
        payment = DriverMonthlyPayment.objects.create(
            driver=self.driver_profile,
            period=timezone.localdate().replace(day=1),
            amount=Decimal("20.00"),
            bank="banco_loja",
            payment_method="transfer",
            receipt_url="storage://movix-documents/monthly-payments/receipt.pdf",
            status="approved",
            reviewed_by=self.admin.username,
            reviewed_at=timezone.now(),
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

        response = self.client.post(reverse("panel:monthly_payment_invoice", args=[payment.id]))

        self.assertEqual(response.status_code, 302)
        invoice = DriverInvoice.objects.get(payment=payment)
        self.assertTrue(invoice.invoice_number.startswith("MOVIX-"))
        self.assertEqual(invoice.pdf_url, "storage://movix-documents/monthly-invoices/factura.pdf")
        self.assertTrue(
            DriverInboxMessage.objects.filter(
                driver=self.driver_profile,
                invoice=invoice,
                message_type="invoice",
            ).exists()
        )
        send_email.assert_called_once()

        self._open_driver_session()
        invoice_list = self.client.get(reverse("panel:driver_invoices"))
        self.assertEqual(invoice_list.status_code, 200)
        self.assertContains(invoice_list, invoice.invoice_number)
        self.assertContains(invoice_list, "Descargar PDF")
        self.assertContains(invoice_list, "Mis facturas")

        payment_history = self.client.get(reverse("panel:driver_payments"))
        self.assertNotContains(payment_history, "Ver factura")

    @patch("panel.views.resolve_media_url", return_value="https://project.supabase.co/storage/v1/object/sign/movix-documents/receipt.pdf?token=ok")
    @patch("panel.views.requests.get")
    def test_driver_can_preview_own_payment_receipt(self, get_mock, _resolve):
        payment = DriverMonthlyPayment.objects.create(
            driver=self.driver_profile, period=timezone.localdate().replace(day=1),
            bank="banco_pichincha", payment_method="transfer",
            receipt_url="storage://movix-documents/monthly-payments/receipt.pdf",
            status="pending", created_at=timezone.now(), updated_at=timezone.now(),
        )
        upstream = Mock(status_code=200)
        upstream.headers = {"Content-Type": "application/pdf", "Content-Length": "7"}
        upstream.iter_content.return_value = iter([b"pdfdata"])
        upstream.raise_for_status.return_value = None
        get_mock.return_value = upstream
        self._open_driver_session()
        response = self.client.get(reverse("panel:monthly_payment_receipt", args=[payment.id, "view"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(response.streaming_content), b"pdfdata")

    def test_ride_detail_uses_client_profile_photo(self):
        self.user_profile.profile_photo_url = "https://project.supabase.co/storage/v1/object/public/movix-public/client.jpg"
        self.user_profile.save(update_fields=["profile_photo_url"])
        ride = self._create_driver_ride()
        self._open_driver_session()
        response = self.client.get(reverse("panel:driver_ride_detail", args=[ride.id]))
        self.assertContains(response, 'alt="Foto de María González"')

    def test_driver_cannot_view_another_drivers_ride(self):
        other_driver = Profile.objects.create(
            id=uuid.uuid4(), role="transportista", first_name="Daniel", last_name="Vera",
            email="daniel@example.com", identification_number="1100000002", is_active=True,
            created_at=timezone.now(), updated_at=timezone.now(),
        )
        ride = self._create_driver_ride(driver=other_driver)
        self._open_driver_session()

        response = self.client.get(reverse("panel:driver_ride_detail", args=[ride.id]))
        self.assertEqual(response.status_code, 404)

    def test_public_contact_request_is_saved(self):
        self.client.logout()
        response = self.client.post(
            reverse("panel:landing"),
            {
                "full_name": "Ana Torres",
                "email": "ana@example.com",
                "phone": "+593990001122",
                "request_type": "service",
                "subject": "Necesito una mudanza",
                "message": "Quiero transportar muebles dentro de Loja.",
                "privacy_accepted": "on",
                "website": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("enviado=1", response.url)
        self.assertTrue(ContactRequest.objects.filter(email="ana@example.com").exists())

    @patch("panel.views.send_movix_email", return_value=(True, ""))
    def test_contact_request_can_be_reviewed_and_answered(self, send_email):
        contact = ContactRequest.objects.create(
            full_name="Ana Torres",
            email="ana@example.com",
            request_type="company",
            subject="Convenio empresarial",
            message="Deseo conocer las opciones para mi empresa.",
        )
        detail_url = reverse("panel:contact_request_detail", args=[contact.id])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        contact.refresh_from_db()
        self.assertEqual(contact.status, ContactRequest.STATUS_READ)

        response = self.client.post(detail_url, {"admin_response": "Con gusto coordinamos una reunión."})
        self.assertEqual(response.status_code, 302)
        contact.refresh_from_db()
        self.assertEqual(contact.status, ContactRequest.STATUS_RESPONDED)
        self.assertEqual(contact.responded_by, "admin_movix")
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.args[0], "ana@example.com")
        self.assertIn("Respuesta MOVIX", send_email.call_args.args[1])
        self.assertIn("Con gusto coordinamos una reunión.", send_email.call_args.args[2])

    def test_dashboard_uses_real_profiles(self):
        response = self.client.get(reverse("panel:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["client_count"], 1)
        self.assertEqual(response.context["driver_count"], 1)

    def test_legacy_verified_boolean_is_shown_as_approved(self):
        self.driver_profile.verification_status = "pending"
        self.driver_profile.profile_verified = True
        self.driver_profile.save(update_fields=["verification_status", "profile_verified"])
        response = self.client.get(reverse("panel:verification_list"))
        self.assertEqual(response.context["counts"]["approved"], 1)
        self.assertContains(response, "Aprobado")

    def test_tables_have_automatic_search_and_document_modal(self):
        listing = self.client.get(reverse("panel:profile_list", args=["users"]))
        self.assertContains(listing, "data-auto-search")
        detail = self.client.get(reverse("panel:verification_detail", args=[self.user_profile.id]))
        self.assertContains(detail, "documentPreviewDialog")
        self.assertContains(detail, "data-document-preview")
        self.assertContains(detail, "asset-preview-card")
        self.assertContains(detail, "asset-preview-frame")
        self.assertContains(detail, "asset-preview-name")
        self.assertContains(detail, "asset-preview-download")
        self.assertContains(detail, "movix-critical-media-v60")
        self.assertContains(detail, "app.css?v=20260824-6", html=False)
        self.assertContains(detail, "app.js?v=20260824-6", html=False)
        self.assertContains(detail, ".document-preview-stage.show-pdf>img{display:none!important}", html=False)

        profile = self.client.get(reverse("panel:profile_detail", args=["users", self.user_profile.id]))
        self.assertContains(profile, "asset-preview-card")
        self.assertContains(profile, "Miniatura de Cédula de identidad")

    @patch("panel.views.resolve_media_url", return_value="")
    def test_missing_storage_object_returns_visible_placeholder(self, _resolve):
        self.user_profile.identification_photo_url = "cedulas/archivo-inexistente.jpg"
        self.user_profile.save(update_fields=["identification_photo_url"])
        response = self.client.get(
            reverse("panel:document_access", args=[self.user_profile.id, "identification", "view"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertEqual(response["X-Movix-Media-Status"], "storage-object-not-found")
        self.assertContains(response, "No se encontró Cédula de identidad")

    @patch("panel.views.requests.get")
    @patch("panel.views.resolve_media_url", return_value="https://project.supabase.co/storage/v1/object/sign/movix-documents/cedula.jpg?token=ok")
    def test_private_document_is_proxied_inline_by_django(self, _resolve, get_mock):
        upstream = Mock(status_code=200)
        upstream.headers = {"Content-Type": "image/jpeg", "Content-Length": "6"}
        upstream.iter_content.return_value = iter([b"imagen"])
        get_mock.return_value = upstream

        response = self.client.get(
            reverse("panel:document_access", args=[self.user_profile.id, "identification", "view"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        self.assertEqual(response["X-Movix-Media-Status"], "proxied")
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(b"".join(response.streaming_content), b"imagen")

    def test_pdf_document_has_embedded_first_page_preview(self):
        self.user_profile.identification_photo_url = "storage://movix-documents/perfiles/cedula.pdf"
        self.user_profile.save(update_fields=["identification_photo_url"])

        response = self.client.get(reverse("panel:verification_detail", args=[self.user_profile.id]))

        self.assertContains(response, "asset-pdf-thumbnail")
        self.assertContains(response, "#page=1&zoom=page-fit", html=False)
        self.assertContains(response, "Primera página de Cédula de identidad")

    @patch("panel.views.requests.get")
    @patch("panel.views.resolve_media_url", return_value="https://project.supabase.co/storage/v1/object/sign/movix-documents/cedula.jpg?token=ok")
    def test_storage_permission_failure_returns_placeholder_instead_of_broken_image(self, _resolve, get_mock):
        upstream = Mock(status_code=403)
        upstream.headers = {"Content-Type": "application/json"}
        get_mock.return_value = upstream

        response = self.client.get(
            reverse("panel:document_access", args=[self.user_profile.id, "identification", "view"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertEqual(response["X-Movix-Media-Status"], "storage-download-failed")

    def test_profile_photo_replaces_initials_when_available(self):
        self.user_profile.profile_photo_url = "https://example.supabase.co/storage/v1/object/public/movix-public/avatar.jpg"
        self.user_profile.save(update_fields=["profile_photo_url"])
        response = self.client.get(reverse("panel:profile_list", args=["users"]))
        self.assertContains(response, 'alt="Foto de María González"')

    def test_profile_lists_and_export(self):
        response = self.client.get(reverse("panel:profile_list", args=["users"]))
        self.assertContains(response, "María González")
        export = self.client.get(reverse("panel:profile_export", args=["drivers"]))
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["Content-Type"], "text/csv; charset=utf-8")

    def test_block_and_unblock(self):
        url = reverse("panel:profile_toggle", args=["users", self.user_profile.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.user_profile.refresh_from_db()
        self.assertFalse(self.user_profile.is_active)
        self.assertTrue(self.user_profile.is_blocked)

    def test_approve_verification_creates_notification(self):
        url = reverse("panel:verification_update", args=[self.user_profile.id, "approve"])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.verification_status, "approved")
        self.assertTrue(Notification.objects.filter(user=self.user_profile, type="verification").exists())

    @patch("panel.views.send_push_notifications", return_value=(0, ""))
    @patch("panel.views.active_tokens_for_users", return_value=[])
    def test_send_internal_notification(self, _tokens, _push):
        response = self.client.post(
            reverse("panel:notifications"),
            {"audience": "all", "recipient": "", "title": "Actualización", "message": "MOVIX tiene una nueva función."},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(NotificationCampaign.objects.count(), 1)

    def test_non_staff_is_forbidden(self):
        normal = User.objects.create_user("lector", password="PruebaSegura123")
        self.client.force_login(normal)
        response = self.client.get(reverse("panel:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_profile_cover_uses_an_image_that_fills_the_card(self):
        AdminProfile.objects.create(user=self.admin, cover_url="https://example.com/portada.jpg")
        response = self.client.get(reverse("panel:admin_profile"))
        self.assertContains(response, 'class="admin-profile-cover-image profile-cover-image"')
        self.assertContains(response, 'src="https://example.com/portada.jpg"')
        self.assertContains(response, "Editar perfil")
        self.assertContains(response, "Información personal")
        self.assertNotContains(response, 'id="id_profile-first_name"')

        editing = self.client.get(reverse("panel:admin_profile") + "?editar=1")
        self.assertContains(editing, "admin-media-upload", count=2)
        self.assertContains(editing, '<span class="local-file-preview"', count=2, html=False)
        self.assertContains(editing, 'id="id_profile-first_name"')
        self.assertContains(editing, "Cancelar edición")

    def test_all_administrative_views_render(self):
        contact = ContactRequest.objects.create(
            full_name="Ana Torres",
            email="ana@example.com",
            subject="Consulta",
            message="Información sobre MOVIX.",
        )
        urls = [
            reverse("panel:profile_detail", args=["users", self.user_profile.id]),
            reverse("panel:profile_detail", args=["drivers", self.driver_profile.id]),
            reverse("panel:profile_create", args=["users"]),
            reverse("panel:profile_create", args=["drivers"]),
            reverse("panel:profile_edit", args=["users", self.user_profile.id]),
            reverse("panel:profile_edit", args=["drivers", self.driver_profile.id]),
            reverse("panel:verification_list"),
            reverse("panel:verification_detail", args=[self.user_profile.id]),
            reverse("panel:verification_detail", args=[self.driver_profile.id]),
            reverse("panel:notifications"),
            reverse("panel:monthly_payment_list"),
            reverse("panel:payment_bank_accounts"),
            reverse("panel:admin_driver_messages"),
            reverse("panel:advertisements"),
            reverse("panel:admin_profile"),
            reverse("panel:settings"),
            reverse("panel:contact_request_list"),
            reverse("panel:contact_request_detail", args=[contact.id]),
            reverse("panel:search") + "?q=María",
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
