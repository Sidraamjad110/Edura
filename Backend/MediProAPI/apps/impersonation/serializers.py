# apps/impersonation/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from MediProAPI.apps.users.models import Client
from MediProAPI.apps.users.models import CustomUser

User = get_user_model()


class UserSearchSerializer(serializers.ModelSerializer):
    """Simple serializer for user search results"""
    user_type = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    client_company = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'full_name', 'user_type', 'is_active', 'avatar',
            'client_company', 'last_login'
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    def get_user_type(self, obj):
        """Determine if user is admin, client, or regular user"""
        if obj.is_staff or obj.is_superuser:
            return 'admin'
        if hasattr(obj, 'client_profile'):
            return 'client'
        if hasattr(obj, 'custom_profile'):
            return 'user'
        return 'unknown'

    def get_avatar(self, obj):
        """Get avatar from respective profile"""
        if hasattr(obj, 'client_profile'):
            return obj.client_profile.avatar
        if hasattr(obj, 'custom_profile'):
            return obj.custom_profile.avatar
        if hasattr(obj, 'admin_profile'):
            return obj.admin_profile.avatar
        return None

    def get_client_company(self, obj):
        """Get company name for client users"""
        if hasattr(obj, 'client_profile'):
            return obj.client_profile.company_name
        return None


class SwitchUserSerializer(serializers.Serializer):
    """Serializer for switch user request"""
    username = serializers.CharField(required=True, write_only=True)

    def validate_username(self, value):
        try:
            user = User.objects.get(username=value, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found or inactive")

        # Check if trying to switch to admin (optional - you can allow or block)
        # if user.is_staff or user.is_superuser:
        #     raise serializers.ValidationError("Cannot switch to admin users")

        return value