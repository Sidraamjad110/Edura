from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("azure_ai_endpoint", models.URLField(blank=True, default="", max_length=500)),
                ("azure_ai_api_key", models.CharField(blank=True, default="", max_length=500)),
                ("azure_openai_endpoint", models.URLField(blank=True, default="", max_length=500)),
                ("azure_openai_api_key", models.CharField(blank=True, default="", max_length=500)),
                ("azure_chat_deployment", models.CharField(blank=True, default="", max_length=255)),
                ("azure_chat_api_version", models.CharField(blank=True, default="", max_length=50)),
                ("azure_embed_deployment", models.CharField(blank=True, default="", max_length=255)),
                ("azure_embed_api_version", models.CharField(blank=True, default="", max_length=50)),
                ("realtime_ws_url", models.URLField(blank=True, default="", max_length=500)),
                ("realtime_api_key", models.CharField(blank=True, default="", max_length=500)),
                ("realtime_api_key_header", models.CharField(blank=True, default="", max_length=255)),
                ("realtime_model_name", models.CharField(blank=True, default="", max_length=255)),
                ("smtp_host", models.CharField(blank=True, default="", max_length=255)),
                ("smtp_port", models.PositiveIntegerField(blank=True, null=True)),
                ("smtp_username", models.CharField(blank=True, default="", max_length=255)),
                ("smtp_password", models.CharField(blank=True, default="", max_length=500)),
                ("smtp_use_ssl", models.BooleanField(default=False)),
                ("smtp_use_tls", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.OneToOneField(
                        db_column="client_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credentials",
                        to="users.client",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="credential_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "credentials_clientcredential",
                "verbose_name": "Client Credential",
                "verbose_name_plural": "Client Credentials",
            },
        ),
    ]
