import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("panel", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ContactRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("full_name", models.CharField(max_length=160)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(blank=True, max_length=30)),
                (
                    "request_type",
                    models.CharField(
                        choices=[
                            ("service", "Solicitar un transporte"),
                            ("driver", "Quiero trabajar con MOVIX"),
                            ("company", "Convenio para empresa"),
                            ("support", "Ayuda o soporte"),
                            ("other", "Otra consulta"),
                        ],
                        default="service",
                        max_length=30,
                    ),
                ),
                ("subject", models.CharField(max_length=180)),
                ("message", models.TextField(max_length=2000)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "Nueva"),
                            ("read", "Leída"),
                            ("responded", "Respondida"),
                            ("closed", "Cerrada"),
                        ],
                        default="new",
                        max_length=20,
                    ),
                ),
                ("admin_response", models.TextField(blank=True, max_length=4000)),
                ("responded_by", models.CharField(blank=True, max_length=150)),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "contact_requests",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["status", "-created_at"], name="contact_status_created_idx"),
                    models.Index(fields=["email"], name="contact_email_idx"),
                ],
            },
        )
    ]
