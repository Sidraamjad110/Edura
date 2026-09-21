# apps/accounts/views.py
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Case, When, IntegerField
from .serializers import LoginSerializer, RegisterSerializer
from ..users.models import Language
from ..modules.models import UserModule
from django.contrib.auth import get_user_model

User = get_user_model()


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def get_user_modules(self, user_id):
        """
        Return a nested tree of modules for the given user.

        ONLY modules that have a row in user_modules for this user_id are
        returned — never anything from the global modules catalogue that
        isn't explicitly assigned.

        Hierarchy is built from UserModule.parent_id (per-user), NOT from
        the Module model (which no longer carries a parent_id column).
        """
        try:
            # ── Fetch only rows that are assigned to this user ──────────────
            user_modules = (
                UserModule.objects
                .select_related('module')
                .filter(
                    user_id=user_id,
                    is_active=True,
                    module__is_active=True,
                )
                .annotate(
                    order_priority=Case(
                        When(is_default=True, then=0),
                        default=1,
                        output_field=IntegerField(),
                    )
                )
                .order_by('order_priority', 'sequence', 'module__code')
            )

            if not user_modules.exists():
                return []

            # ── Pass 1: build a flat dict keyed by module_id ────────────────
            # parent_id here is UserModule.parent_id — the per-user hierarchy.
            module_dict: dict = {}
            for um in user_modules:
                module_dict[um.module_id] = {
                    'id':                   um.module_id,
                    'code':                 um.module.code,
                    'description':          um.module.description,
                    'icon':                 um.module.icon,
                    'url':                  um.module.url,
                    'parent_id':            um.parent_id,       # UserModule.parent_id
                    'is_active':            um.module.is_active,
                    'user_module_id':       um.id,
                    'sequence':             um.sequence,
                    'is_default':           um.is_default,
                    'user_module_is_active': um.is_active,
                    'show_in_sidebar':      um.show_in_sidebar,
                    'children':             [],
                }

            # ── Pass 2: wire children to their parents ──────────────────────
            # A valid parent must itself be assigned to this user.
            # If parent_id points to a module not in this user's assignment,
            # treat it as top-level (orphan promotion).
            root_modules: list = []
            assigned_module_ids = set(module_dict.keys())

            for um in user_modules:
                node      = module_dict[um.module_id]
                parent_id = um.parent_id   # UserModule.parent_id

                if parent_id is not None and parent_id in assigned_module_ids:
                    # Valid parent — attach as child
                    module_dict[parent_id]['children'].append(node)
                else:
                    # No parent or parent not assigned to this user → root
                    node['parent_id'] = None   # normalise orphan parent refs
                    root_modules.append(node)

            # ── Sort children and roots by sequence ─────────────────────────
            for node in module_dict.values():
                if node['children']:
                    node['children'].sort(
                        key=lambda x: (x['sequence'] or 9999, x['code'])
                    )

            root_modules.sort(
                key=lambda x: (0 if x['is_default'] else 1, x['sequence'] or 9999, x['code'])
            )

            from EduraAPI.apps.modules.catalog import filter_module_tree
            return filter_module_tree(root_modules)

        except Exception as e:
            print(f"Error fetching user modules: {e}")
            return []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Generate JWT tokens
            refresh      = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)

            response_data = {
                "user_id":      user.id,
                "username":     user.username,
                "email":        user.email,
                "first_name":   user.first_name,
                "last_name":    user.last_name,
                "full_name":    f"{user.first_name} {user.last_name}".strip() or user.username,
                "is_superuser": user.is_superuser,
                "is_active":    user.is_active,
                "access_token": access_token,
                "refresh_token": str(refresh),
            }

            # Modules — strictly from user_modules assignment
            if hasattr(user, "client_profile"):
                from EduraAPI.apps.subscription.services.plan_modules import assign_client_sidebar_modules
                assign_client_sidebar_modules(user)

            user_modules = self.get_user_modules(user.id)
            response_data["modules"] = user_modules
            response_data["modules_count"] = len(user_modules)

            roles         = []
            user_type     = None
            language      = None
            language_name = None

            # All languages list
            try:
                languages_list = (
                    Language.objects.filter(is_active=True)
                    .values('id', 'code', 'name')
                    .order_by('name')
                )
                response_data["languages"] = list(languages_list)
            except Exception as e:
                print(f"Error fetching languages: {e}")
                response_data["languages"] = []

            # ── Client ──────────────────────────────────────────────────────
            if hasattr(user, 'client_profile'):
                client    = user.client_profile
                user_type = "client"

                response_data["client_id"]    = client.id
                response_data["auth_user_id"] = user.id

                if client.language:
                    language      = client.language.code
                    language_name = client.language.name

                response_data["company_name"] = client.company_name
                response_data["phone"]        = client.phone
                response_data["avatar"]       = client.avatar

            # ── CustomUser ──────────────────────────────────────────────────
            elif hasattr(user, 'custom_profile'):
                custom_user = user.custom_profile
                user_type   = "custom_user"

                response_data["user_id"]             = custom_user.id
                response_data["auth_user_id"]        = user.id
                response_data["client_id"]           = custom_user.client.id
                response_data["client_auth_user_id"] = custom_user.client.auth_user_id
                response_data["client_username"]     = custom_user.client.auth_user.username
                response_data["client_company"]      = custom_user.client.company_name
                response_data["phone"]               = custom_user.phone
                response_data["avatar"]              = custom_user.avatar

                if custom_user.language:
                    language      = custom_user.language.code
                    language_name = custom_user.language.name

            # ── Superuser / Admin ────────────────────────────────────────────
            elif user.is_superuser:
                user_type = "admin"
                roles     = ["Admin"]
                try:
                    english_language = Language.objects.filter(code='en').first()
                    if english_language:
                        language      = english_language.code
                        language_name = english_language.name
                    else:
                        language      = 'en'
                        language_name = 'English'
                except Exception as e:
                    print(f"Error fetching English language: {e}")
                    language      = 'en'
                    language_name = 'English'

                if hasattr(user, 'admin_profile'):
                    admin = user.admin_profile
                    response_data["phone"]  = admin.phone
                    response_data["avatar"] = admin.avatar

            # Module-level roles — empty for client/custom_user; copy of roles for admin.
            module_roles = list(roles) if user_type == "admin" else []
            response_data["module_roles"] = module_roles

            response_data["user_type"]     = user_type
            response_data["language"]      = language
            response_data["language_name"] = language_name
            response_data["roles"]         = roles

            return Response(response_data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            refresh      = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)

            response_data = {
                "user_id":        user.id,
                "username":       user.username,
                "email":          user.email,
                "first_name":     user.first_name,
                "last_name":      user.last_name,
                "full_name":      f"{user.first_name} {user.last_name}".strip() or user.username,
                "user_type":      "admin" if user.is_superuser else None,
                "language":       None,
                "roles":          [],
                "is_superuser":   user.is_superuser,
                "is_active":      user.is_active,
                "access_token":   access_token,
                "refresh_token":  str(refresh),
                "modules":        [],
                "modules_count":  0,
            }

            return Response(response_data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)