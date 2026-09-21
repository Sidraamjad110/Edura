from django.contrib import admin
from .models import ClientCredential


@admin.register(ClientCredential)
class ClientCredentialAdmin(admin.ModelAdmin):
    list_display = ["client", "smtp_host", "azure_chat_deployment", "updated_at", "updated_by"]
    list_filter = ["smtp_use_ssl", "smtp_use_tls"]
    search_fields = ["client__name", "smtp_host", "azure_chat_deployment"]
    readonly_fields = ["created_at", "updated_at", "updated_by"]

    fieldsets = (
        ("Client", {"fields": ("client",)}),
        (
            "Azure AI",
            {
                "fields": ("azure_ai_endpoint", "azure_ai_api_key"),
                "classes": ("collapse",),
            },
        ),
        (
            "Azure OpenAI",
            {
                "fields": (
                    "azure_openai_endpoint",
                    "azure_openai_api_key",
                    "azure_chat_deployment",
                    "azure_chat_api_version",
                    "azure_embed_deployment",
                    "azure_embed_api_version",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Real-time / Agent",
            {
                "fields": (
                    "realtime_ws_url",
                    "realtime_api_key",
                    "realtime_api_key_header",
                    "realtime_model_name",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "SMTP / Email",
            {
                "fields": (
                    "smtp_host",
                    "smtp_port",
                    "smtp_username",
                    "smtp_password",
                    "smtp_use_ssl",
                    "smtp_use_tls",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at", "updated_by")}),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)