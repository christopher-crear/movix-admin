import uuid
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django import forms
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, SimpleTestCase, TransactionTestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import ProfileCreateForm, ProfileForm, PublicContactForm
from .models import (
    Advertisement,
    AuditLog,
    ContactRequest,
    DeviceToken,
    DriverReview,
    Notification,
    NotificationCampaign,
    Profile,
    Ride,
    SystemSetting,
)
from .services import upload_to_supabase


EXTERNAL_MODELS = [Profile, Ride, DriverReview, Notification, Advertisement, NotificationCampaign, DeviceToken, AuditLog, SystemSetting]


class PublicPagesTests(SimpleTestCase):
    def test_landing_page_renders(self):
        response = self.client.get(reverse("panel:landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Transporte de carga en Loja")
        self.assertContains(response, "data-floating-phone")

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bienvenido, administrador")

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(reverse("panel:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class FormTests(SimpleTestCase):
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

    def test_contact_request_can_be_reviewed_and_answered(self):
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
