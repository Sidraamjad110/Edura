from rest_framework import serializers
from .models import ClientCredential

# Fields treated as secrets — masked on read, preserved if sent back as "*****"
CREDENTIAL_SECRET_FIELDS = (
    "azure_ai_api_key",
    "azure_openai_api_key",
    "realtime_api_key",
    "smtp_password",
)


def mask_secret(value: str, visible: int = 4) -> str:
    """Mirrors the mask_secret() helper from client_telephony_resolver."""
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= visible:
        return "*" * len(cleaned)
    return "*" * (len(cleaned) - visible) + cleaned[-visible:]


class ClientCredentialSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    client_company = serializers.CharField(source="client.company_name", read_only=True)
    secrets_set = serializers.SerializerMethodField()

    class Meta:
        model = ClientCredential
        fields = [
            "id",
            "client",
            "client_name",
            "client_company",
            # Azure AI
            "azure_ai_endpoint",
            "azure_ai_api_key",
            # Azure OpenAI
            "azure_openai_endpoint",
            "azure_openai_api_key",
            # Chat
            "azure_chat_deployment",
            "azure_chat_api_version",
            # Embed
            "azure_embed_deployment",
            "azure_embed_api_version",
            # Realtime
            "realtime_ws_url",
            "realtime_api_key",
            "realtime_api_key_header",
            "realtime_model_name",
            # SMTP
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_password",
            "smtp_use_ssl",
            "smtp_use_tls",
            # Meta
            "secrets_set",
            "created_at",
            "updated_at",
            "updated_by",
        ]
        read_only_fields = [
            "id",
            "client",
            "client_name",
            "client_company",
            "secrets_set",
            "created_at",
            "updated_at",
            "updated_by",
        ]

    def get_client_name(self, obj):
        if not obj.client or not obj.client.auth_user:
            return ""
        return obj.client.auth_user.get_full_name() or obj.client.auth_user.username

    def get_secrets_set(self, obj):
        """
        Mirrors telephony's secrets_set — tells the frontend which secret
        fields have a saved value without exposing the value itself.
        """
        return {field: bool(getattr(obj, field, "")) for field in CREDENTIAL_SECRET_FIELDS}

    def to_representation(self, instance):
        """Mask secret field values on read — mirrors telephony serializer."""
        data = super().to_representation(instance)
        for field in CREDENTIAL_SECRET_FIELDS:
            raw = getattr(instance, field, "")
            if raw:
                data[field] = mask_secret(raw)
        return data

    def _preserve_secrets(self, validated_data):
        """
        If the frontend sends back a masked placeholder ("****...") for a
        secret field, drop it from validated_data so the stored value is
        never overwritten with the mask itself.
        Mirrors telephony's _preserve_secrets().
        """
        instance = getattr(self, "instance", None)
        if not instance:
            return validated_data
        for field in CREDENTIAL_SECRET_FIELDS:
            incoming = self.initial_data.get(field)
            if incoming is None:
                continue
            cleaned = str(incoming).strip()
            if not cleaned or cleaned.startswith("*"):
                validated_data.pop(field, None)
        return validated_data

    def create(self, validated_data):
        validated_data = self._preserve_secrets(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data = self._preserve_secrets(validated_data)
        return super().update(instance, validated_data)