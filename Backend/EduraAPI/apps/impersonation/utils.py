# apps/authentication/utils.py
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.settings import api_settings
from django.contrib.auth import get_user_model
from datetime import timedelta, datetime
import json

User = get_user_model()


def get_tokens_for_user(user, additional_claims=None):
    """Generate JWT tokens for user with optional additional claims"""
    refresh = RefreshToken.for_user(user)

    # Add default claims
    refresh['user_id'] = user.id
    refresh['username'] = user.username
    refresh['email'] = user.email

    # Check if user is admin
    refresh['is_admin'] = user.is_staff or user.is_superuser

    # Check if user has client profile
    refresh['is_client'] = hasattr(user, 'client_profile')

    # Check if user has custom profile
    refresh['is_custom_user'] = hasattr(user, 'custom_profile')

    # Add additional claims (for impersonation)
    if additional_claims:
        for key, value in additional_claims.items():
            refresh[key] = value

    access = refresh.access_token

    return {
        'refresh': str(refresh),
        'access': str(access)
    }


def generate_impersonation_token(admin_user, target_user):
    """
    Generate token for admin impersonating target user
    """
    additional_claims = {
        'impersonating': True,
        'original_admin_id': admin_user.id,
        'original_admin_username': admin_user.username,
        'impersonated_user_id': target_user.id,
        'impersonated_username': target_user.username,
        'impersonation_started': datetime.now().isoformat()
    }

    # Set shorter expiry for impersonation tokens (30 minutes)
    original_expiry = api_settings.ACCESS_TOKEN_LIFETIME
    api_settings.ACCESS_TOKEN_LIFETIME = timedelta(minutes=30)

    tokens = get_tokens_for_user(target_user, additional_claims)

    # Restore original expiry
    api_settings.ACCESS_TOKEN_LIFETIME = original_expiry

    return tokens