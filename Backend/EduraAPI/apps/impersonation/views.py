# apps/impersonation/views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from django.contrib.auth import get_user_model
from django.db.models import Q, When,IntegerField,Case
from django.utils import timezone
from django.db import connection
from .serializers import SwitchUserSerializer, UserSearchSerializer
from .models import ImpersonationLog
import json
from ..modules.models import UserModule

User = get_user_model()


# ============================================
# HELPER FUNCTION: Get user modules (copied from LoginAPIView)
# ============================================
def get_user_modules(user_id):
    """
    Helper function to get user modules with sequence and default flag
    Returns a hierarchical list of modules with children nested under parents
    """
    try:
        # Get all user modules with related module data
        user_modules = UserModule.objects.select_related('module').filter(
            user_id=user_id,
            is_active=True,
            module__is_active=True
        ).annotate(
            # Create ordering field: default modules first, then by sequence, then by code
            order_priority=Case(
                When(is_default=True, then=0),
                default=1,
                output_field=IntegerField()
            )
        ).order_by('order_priority', 'sequence', 'module__code')

        # First pass: create a dictionary of all modules
        module_dict = {}
        parent_modules = []

        for um in user_modules:
            module = um.module
            formatted_module = {
                'id': module.id,
                'code': module.code,
                'description': module.description,
                'icon': module.icon,
                'url': module.url,
                'parent_id': um.parent_id,  # parent_id comes from UserModule
                'is_active': module.is_active,
                'user_module_id': um.id,
                'sequence': um.sequence,
                'is_default': um.is_default,
                'user_module_is_active': um.is_active,
                'show_in_sidebar': um.show_in_sidebar,
                'children': []  # Initialize empty children list
            }
            module_dict[module.id] = formatted_module

        # Second pass: build hierarchy based on parent_id from UserModule
        for um in user_modules:
            formatted_module = module_dict[um.module_id]
            parent_id = um.parent_id

            if parent_id is None:
                # This is a top-level module
                parent_modules.append(formatted_module)
            else:
                # This is a child module - add to parent's children list
                if parent_id in module_dict:
                    module_dict[parent_id]['children'].append(formatted_module)
                else:
                    # Parent not found in user's modules, treat as top-level
                    parent_modules.append(formatted_module)

        # Sort children by sequence and code
        for module in module_dict.values():
            if module['children']:
                module['children'].sort(key=lambda x: (x['sequence'] or 9999, x['code']))

        # Sort top-level modules
        parent_modules.sort(key=lambda x: (0 if x['is_default'] else 1, x['sequence'] or 9999, x['code']))

        from EduraAPI.apps.modules.catalog import filter_module_tree
        return filter_module_tree(parent_modules)

    except Exception as e:
        # Log error if needed
        print(f"Error fetching modules: {e}")
        return []


# ============================================
# HELPER FUNCTION: Get user profile data (copied from LoginAPIView)
# ============================================
def get_user_profile_data(user):
    """
    Helper function to get complete user profile data including roles, language, etc.
    """
    roles = []
    user_type = None
    language = None
    language_name = None

    # Get languages list
    languages_list = []
    try:
        from EduraAPI.apps.users.models import Language
        languages_list = list(Language.objects.filter(is_active=True).values('id', 'code', 'name').order_by('name'))
    except Exception as e:
        print(f"Error fetching languages: {e}")

    # Check if user is a Client
    if hasattr(user, 'client_profile'):
        client = user.client_profile
        user_type = "client"

        # Get language
        if client.language:
            language = client.language.code
            language_name = client.language.name

        return {
            'user_id': user.id,
            'auth_user_id': user.id,
            'client_id': client.id,
            'user_type': user_type,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'phone': client.phone,
            'company_name': client.company_name,
            'avatar': client.avatar,
            'language': language,
            'language_name': language_name,
            'roles': roles,
            'is_client': True,
            'is_custom_user': False,
            'is_admin': False,
            'languages': languages_list
        }

    # Check if user is a CustomUser
    elif hasattr(user, 'custom_profile'):
        custom_user = user.custom_profile
        user_type = "custom_user"

        if custom_user.language:
            language = custom_user.language.code
            language_name = custom_user.language.name

        return {
            'user_id': custom_user.id,
            'auth_user_id': user.id,
            'client_id': custom_user.client.id,
            'user_type': user_type,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'phone': custom_user.phone,
            'avatar': custom_user.avatar,
            'client_auth_user_id': custom_user.client.auth_user_id,
            'client_username': custom_user.client.auth_user.username,
            'client_company': custom_user.client.company_name,
            'language': language,
            'language_name': language_name,
            'roles': roles,
            'is_client': False,
            'is_custom_user': True,
            'is_admin': False,
            'languages': languages_list
        }

    # Admin user
    else:
        user_type = "admin"
        roles = ["Admin"]

        profile_data = {
            'user_id': user.id,
            'auth_user_id': user.id,
            'user_type': user_type,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'phone': None,
            'avatar': None,
            'language': language,
            'language_name': language_name,
            'roles': roles,
            'is_client': False,
            'is_custom_user': False,
            'is_admin': True,
            'languages': languages_list
        }

        # Add admin profile if exists
        if hasattr(user, 'admin_profile'):
            admin = user.admin_profile
            profile_data['phone'] = admin.phone
            profile_data['avatar'] = admin.avatar

        return profile_data


# ============================================
# TOKEN GENERATION FUNCTIONS
# ============================================
def generate_impersonation_token(admin_user, target_user):
    """
    Generate token for admin impersonating target user
    WITH PROPER IMPERSONATION CLAIMS
    """
    refresh = RefreshToken.for_user(target_user)

    # Add impersonation claims
    refresh['impersonating'] = True
    refresh['original_admin_id'] = admin_user.id
    refresh['original_admin_username'] = admin_user.username
    refresh[
        'original_admin_full_name'] = f"{admin_user.first_name} {admin_user.last_name}".strip() or admin_user.username

    # Add user type claims
    refresh['is_admin'] = target_user.is_staff or target_user.is_superuser
    refresh['is_client'] = hasattr(target_user, 'client_profile')
    refresh['is_custom_user'] = hasattr(target_user, 'custom_profile')

    # Add user identification
    refresh['user_id'] = target_user.id
    refresh['username'] = target_user.username
    refresh['email'] = target_user.email

    # Add timestamp
    from datetime import datetime
    refresh['impersonation_started'] = datetime.now().isoformat()

    access = refresh.access_token

    return {
        'access': str(access),
        'refresh': str(refresh)
    }


def get_tokens_for_user(user, additional_claims=None):
    """
    Generate tokens for regular login
    """
    refresh = RefreshToken.for_user(user)

    refresh['user_id'] = user.id
    refresh['username'] = user.username
    refresh['email'] = user.email
    refresh['is_admin'] = user.is_staff or user.is_superuser
    refresh['is_client'] = hasattr(user, 'client_profile')
    refresh['is_custom_user'] = hasattr(user, 'custom_profile')

    if additional_claims:
        for key, value in additional_claims.items():
            refresh[key] = value

    access = refresh.access_token

    return {
        'access': str(access),
        'refresh': str(refresh)
    }


class UserSearchView(APIView):
    """Search users by username, email, or full name"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {'error': 'Only admins can search users'},
                status=status.HTTP_403_FORBIDDEN
            )

        query = request.GET.get('q', '')
        if len(query) < 2:
            return Response({'results': []})

        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).filter(is_active=True).exclude(id=request.user.id)[:10]

        serializer = UserSearchSerializer(users, many=True)
        return Response({'results': serializer.data})


class SwitchUserView(APIView):
    """Admin switches to another user - WITH MODULES FETCHED"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {'error': 'Only admins can switch users'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = SwitchUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        username = serializer.validated_data['username']

        try:
            target_user = User.objects.get(username=username, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if target_user.id == request.user.id:
            return Response(
                {'error': 'Cannot switch to yourself'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generate impersonation token
        tokens = generate_impersonation_token(request.user, target_user)

        # Log the impersonation
        ImpersonationLog.objects.create(
            admin_user=request.user,
            target_user=target_user,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        # ✅ GET USER MODULES FOR THE TARGET USER
        user_modules = get_user_modules(target_user.id)

        # ✅ GET COMPLETE USER PROFILE DATA
        user_profile = get_user_profile_data(target_user)

        # Module-level roles
        module_roles = list(user_profile.get('roles') or []) if user_profile.get('is_admin') else []

        response_data = {
            'success': True,
            'access_token': tokens['access'],
            'refresh_token': tokens['refresh'],
            'impersonating': True,
            'original_admin': {
                'id': request.user.id,
                'username': request.user.username,
                'full_name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
            },
            'user': user_profile,
            'modules': user_modules,
            'modules_count': len(user_modules),
            "module_roles" : module_roles,
            'dashboard': f"/{user_profile['user_type']}/dashboard"
        }

        return Response(response_data)


class ReturnToAdminView(APIView):
    """Return from impersonated user back to admin - WITH MODULES FETCHED"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                access_token = AccessToken(token)
                impersonating = access_token.get('impersonating', False)
                original_admin_id = access_token.get('original_admin_id')

                if not impersonating or not original_admin_id:
                    return Response(
                        {'error': 'Not in impersonation mode'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                try:
                    admin_user = User.objects.get(id=original_admin_id, is_active=True)
                except User.DoesNotExist:
                    return Response(
                        {'error': 'Original admin user not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )

                # Update impersonation log
                ImpersonationLog.objects.filter(
                    admin_user=admin_user,
                    target_user=request.user,
                    ended_at__isnull=True
                ).update(ended_at=timezone.now())

                # Generate new token for admin
                tokens = get_tokens_for_user(admin_user, {
                    'is_admin': True,
                    'impersonating': False,
                    'is_client': False,
                    'is_custom_user': False
                })

                # ✅ GET ADMIN MODULES
                admin_modules = get_user_modules(admin_user.id)

                # ✅ GET COMPLETE ADMIN PROFILE DATA
                admin_profile = get_user_profile_data(admin_user)

                # Module-level roles
                module_roles = list(admin_profile.get('roles') or []) if admin_profile.get('is_admin') else []

                return Response({
                    'success': True,
                    'access_token': tokens['access'],
                    'refresh_token': tokens['refresh'],
                    'impersonating': False,
                    'user': admin_profile,
                    'modules': admin_modules,
                    'modules_count': len(admin_modules),
                    "module_roles": module_roles,
                    'dashboard': '/admin'
                })

            except Exception as e:
                print(f"Error in return to admin: {str(e)}")
                return Response(
                    {'error': 'Invalid token'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(
            {'error': 'Authorization header missing'},
            status=status.HTTP_401_UNAUTHORIZED
        )


class CheckImpersonationView(APIView):
    """Check if current session is impersonating"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                access_token = AccessToken(token)
                impersonating = access_token.get('impersonating', False)

                response_data = {
                    'impersonating': impersonating,
                    'original_admin_id': access_token.get('original_admin_id'),
                    'original_admin_username': access_token.get('original_admin_username'),
                    'original_admin_full_name': access_token.get('original_admin_full_name'),
                    'impersonated_user_id': access_token.get('user_id'),
                    'impersonated_username': access_token.get('username'),
                    'impersonation_started': access_token.get('impersonation_started'),
                    'is_admin': access_token.get('is_admin', False),
                    'is_client': access_token.get('is_client', False),
                    'is_custom_user': access_token.get('is_custom_user', False)
                }

                return Response(response_data)

            except Exception as e:
                print(f"Error checking impersonation: {str(e)}")
                pass

        return Response({
            'impersonating': False
        })