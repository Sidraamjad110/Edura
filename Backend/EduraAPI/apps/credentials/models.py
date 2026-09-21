from django.db import models
from django.conf import settings
from EduraAPI.apps.users.models import Client


class ClientCredential(models.Model):
    """
    Stores all API credentials for a client.
    Each client has exactly one credential record.
    """

    client = models.OneToOneField(
        Client,
        on_delete=models.CASCADE,
        related_name="credentials",
        db_column="client_id",
    )

    # ── Azure AI (generic) ──────────────────────────────────────────────────
    azure_ai_endpoint = models.URLField(max_length=500, blank=True, default="")
    azure_ai_api_key = models.CharField(max_length=500, blank=True, default="")

    # ── Azure OpenAI ────────────────────────────────────────────────────────
    azure_openai_endpoint = models.URLField(max_length=500, blank=True, default="")
    azure_openai_api_key = models.CharField(max_length=500, blank=True, default="")

    # ── Chat deployment ─────────────────────────────────────────────────────
    azure_chat_deployment = models.CharField(max_length=255, blank=True, default="")
    azure_chat_api_version = models.CharField(max_length=50, blank=True, default="")

    # ── Embed deployment ────────────────────────────────────────────────────
    azure_embed_deployment = models.CharField(max_length=255, blank=True, default="")
    azure_embed_api_version = models.CharField(max_length=50, blank=True, default="")

    # ── Real-time / Agent (WebSocket) ───────────────────────────────────────
    realtime_ws_url = models.URLField(max_length=500, blank=True, default="")
    realtime_api_key = models.CharField(max_length=500, blank=True, default="")
    realtime_api_key_header = models.CharField(max_length=255, blank=True, default="")
    realtime_model_name = models.CharField(max_length=255, blank=True, default="")

    # ── SMTP / Email ────────────────────────────────────────────────────────
    smtp_host = models.CharField(max_length=255, blank=True, default="")
    smtp_port = models.PositiveIntegerField(blank=True, null=True)
    smtp_username = models.CharField(max_length=255, blank=True, default="")
    smtp_password = models.CharField(max_length=500, blank=True, default="")
    smtp_use_ssl = models.BooleanField(default=False)
    smtp_use_tls = models.BooleanField(default=True)

    # ── Audit ────────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credential_updates",
    )

    class Meta:
        db_table = "credentials_clientcredential"
        verbose_name = "Client Credential"
        verbose_name_plural = "Client Credentials"

    def __str__(self):
        return f"Credentials – {self.client}"