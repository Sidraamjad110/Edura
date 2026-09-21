from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.views import APIView
import base64
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny  # ✅ ADD THIS IMPORT
import pyodbc


from .models import Client, CustomUser, AdminProfile, Language, Localization
from .serializers import (
    ClientSerializer,
    ClientCreateUpdateSerializer,
    CustomUserSerializer,
    CustomUserCreateUpdateSerializer,
    LanguageSerializer,
    LocalizationSerializer,
    LocalizationCreateUpdateSerializer
)

try:
    from EduraAPI.apps.subscription.models import ClientSubscription, SubscriptionPlan
except ImportError:
    ClientSubscription = None
    SubscriptionPlan = None
User = get_user_model()


# ================ LOCALIZATION VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])



def localization_list(request):
    """Get all localizations with filters"""
    language_code = request.GET.get('language_code')
    search = request.GET.get('search')

    localizations = Localization.objects.all().select_related('language', 'created_by')

    if language_code:
        localizations = localizations.filter(language__code=language_code)

    if search:
        localizations = localizations.filter(
            Q(code__icontains=search) |
            Q(text__icontains=search)
        )

    serializer = LocalizationSerializer(localizations, many=True)
    return Response({
        "success": True,
        "message": "Localizations retrieved successfully",
        "data": serializer.data
    })


@api_view(['POST'])
# @permission_classes([IsAuthenticated])


# def localization_bulk_fetch(request):
#     """
#     Fetch all localizations for a specific module and language
#     """
#     language_code = request.data.get('language_code')
#     module_id = request.data.get('module_id')
#
#     if not language_code or not module_id:
#         return Response({
#             "success": False,
#             "message": "Both language_code and module_id are required"
#         }, status=status.HTTP_400_BAD_REQUEST)
#
#     try:
#         language = Language.objects.get(code=language_code, is_active=True)
#     except Language.DoesNotExist:
#         return Response({
#             "success": False,
#             "message": "Language not found or inactive"
#         }, status=status.HTTP_404_NOT_FOUND)
#
#     # Fetch all records belonging to the module
#     localizations = Localization.objects.filter(
#         language=language,
#         module_id=module_id
#     ).values('code', 'text')
#
#     if not localizations.exists():
#          return Response({
#             "success": True,
#             "localizations": {},
#             "message": "No translations found for this module"
#         })
#
#     localization_dict = {loc['code']: loc['text'] for loc in localizations}
#
#     return Response({
#         "success": True,
#         "localizations": localization_dict,
#         "language_code": language_code,
#         "module_id": module_id
#     })
def localization_bulk_fetch(request):
    """
    Fetch localizations for a specific module (or global if module_id is null)
    """
    language_code = request.data.get('language_code')
    # If module_id is not provided or is an empty string/null, use None
    module_id = request.data.get('module_id') or None

    if not language_code:
        return Response({
            "success": False,
            "message": "language_code is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        language = Language.objects.get(code=language_code, is_active=True)
    except Language.DoesNotExist:
        return Response({
            "success": False,
            "message": "Language not found or inactive"
        }, status=status.HTTP_404_NOT_FOUND)

    # Fetch records. Using module_id=None in Django translates to "WHERE module_id IS NULL"
    localizations = Localization.objects.filter(
        language=language,
        module_id=module_id
    ).values('code', 'text')

    localization_dict = {loc['code']: loc['text'] for loc in localizations}

    return Response({
        "success": True,
        "localizations": localization_dict,
        "language_code": language_code,
        "module_id": module_id  # Will return null in JSON if it was global
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def localization_create(request):
    """Create new localization (only superuser)"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to create localizations"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = LocalizationCreateUpdateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        localization = serializer.save()
        full_serializer = LocalizationSerializer(localization)
        return Response({
            "success": True,
            "message": "Localization created successfully",
            "data": full_serializer.data
        }, status=status.HTTP_201_CREATED)

    return Response({
        "success": False,
        "message": "Validation failed",
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def localization_update(request, pk):
    """Update localization (only superuser)"""
    localization = get_object_or_404(Localization, pk=pk)

    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to update localizations"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = LocalizationCreateUpdateSerializer(localization, data=request.data, partial=True)
    if serializer.is_valid():
        localization = serializer.save()
        full_serializer = LocalizationSerializer(localization)
        return Response({
            "success": True,
            "message": "Localization updated successfully",
            "data": full_serializer.data
        })

    return Response({
        "success": False,
        "message": "Validation failed",
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def localization_delete(request, pk):
    """Delete localization (only superuser)"""
    localization = get_object_or_404(Localization, pk=pk)

    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to delete localizations"
        }, status=status.HTTP_403_FORBIDDEN)

    localization.delete()
    return Response({
        "success": True,
        "message": "Localization deleted successfully"
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def localization_detail(request, pk):
    """Get single localization details"""
    localization = get_object_or_404(
        Localization.objects.select_related('language', 'created_by'), pk=pk)

    serializer = LocalizationSerializer(localization)
    return Response({
        "success": True,
        "message": "Localization retrieved successfully",
        "data": serializer.data
    })


# ================ LANGUAGE VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def language_list(request):
    """Get all languages (active only by default)"""
    show_all = request.GET.get('show_all', 'false').lower() == 'true'

    languages = Language.objects.all()

    if not show_all:
        languages = languages.filter(is_active=True)

    serializer = LanguageSerializer(languages, many=True)
    return Response({
        "success": True,
        "message": "Languages retrieved successfully",
        "data": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def account_list(request):
    """
    Admin  -> All clients
    Client -> Users of own client
    Custom user -> Teammates of same client
    """

    auth_user = request.user

    # ================= CUSTOM USER LOGIN =================
    if hasattr(auth_user, 'custom_profile'):
        custom_profile = auth_user.custom_profile
        users = CustomUser.objects.filter(
            client=custom_profile.client,
            is_active=True,
        ).exclude(
            auth_user=auth_user
        ).select_related(
            'auth_user', 'client', 'created_by', 'language'
        )

        serializer = CustomUserSerializer(users, many=True)
        data = serializer.data
        for i, user in enumerate(users):
            data[i]['avatar'] = user.avatar

        return Response({
            "success": True,
            "entity": "users",
            "message": "Team members retrieved successfully",
            "data": data
        })

    # ================= CLIENT LOGIN =================
    if hasattr(auth_user, 'client_profile'):
        users = CustomUser.objects.filter(
            client=auth_user.client_profile
        ).select_related(
            'auth_user', 'client', 'created_by', 'language'
        )

        serializer = CustomUserSerializer(users, many=True)

        # Add avatar to each user
        data = serializer.data
        for i, user in enumerate(users):
            data[i]['avatar'] = user.avatar  # Uses the @property that returns base64 data URI

        return Response({
            "success": True,
            "entity": "users",
            "message": "Users retrieved successfully",
            "data": data
        })

    # ================= ADMIN LOGIN =================
    if auth_user.is_superuser:
        clients = Client.objects.all().select_related(
            'auth_user', 'created_by', 'language'
        )

        serializer = ClientSerializer(clients, many=True)

        # Add avatar to each client
        data = serializer.data
        for i, client in enumerate(clients):
            data[i]['avatar'] = client.avatar  # Uses the @property that returns base64 data URI

        return Response({
            "success": True,
            "entity": "clients",
            "message": "Clients retrieved successfully",
            "data": data
        })

    # ================= FALLBACK =================
    return Response({
        "success": False,
        "message": "Access denied"
    }, status=403)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def account_create(request):
    """
    Unified create API
    Admin  -> Create Client
    Client -> Create User (own client only)
    """

    auth_user = request.user

    # ================= CLIENT LOGIN → CREATE USER =================
    if hasattr(auth_user, 'client_profile'):
        from EduraAPI.apps.subscription.services.access import check_can_create_user

        client_profile = auth_user.client_profile
        user_check = check_can_create_user(client_profile, user=auth_user)
        if not user_check.allowed:
            return Response({
                "success": False,
                "message": user_check.message,
                "code": user_check.code,
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()
        data['client_id'] = auth_user.client_profile.id

        serializer = CustomUserCreateUpdateSerializer(data=data)
        if serializer.is_valid():
            user = serializer.save()
            user.created_by = auth_user
            user.save()

            return Response({
                "success": True,
                "entity": "user",
                "message": "User created successfully",
                "data": CustomUserSerializer(user).data
            }, status=status.HTTP_201_CREATED)

        return Response({
            "success": False,
            "message": "Validation failed",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    # ================= ADMIN LOGIN → CREATE CLIENT =================
    if auth_user.is_superuser:
        serializer = ClientCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            client = serializer.save()
            client.created_by = auth_user
            client.save()

            return Response({
                "success": True,
                "entity": "client",
                "message": "Client created successfully",
                "data": ClientSerializer(client).data
            }, status=status.HTTP_201_CREATED)

        return Response({
            "success": False,
            "message": "Validation failed",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    # ================= FALLBACK =================
    return Response({
        "success": False,
        "message": "You do not have permission to perform this action"
    }, status=status.HTTP_403_FORBIDDEN)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def account_update(request, pk):
    """
    Unified update API that handles three user types:
    1. Admin (superuser) - can update themselves, clients, and custom users
    2. Client - can update themselves and their created users
    3. Custom User - can only update themselves
    """

    user = request.user

    # ================= ADMIN (SUPERUSER) =================
    if user.is_superuser:
        if str(user.id) == str(pk):
            # Get or create AdminProfile
            admin_profile, _ = AdminProfile.objects.get_or_create(auth_user=user)

            if 'first_name' in request.data:
                user.first_name = request.data['first_name']
            if 'last_name' in request.data:
                user.last_name = request.data['last_name']
            if 'email' in request.data:
                user.email = request.data['email']
            if 'phone' in request.data:
                admin_profile.phone = request.data['phone']

            # Handle avatar upload
            avatar_file = request.FILES.get('avatar')
            if avatar_file:
                file_content = avatar_file.read()
                admin_profile.avatar_base64 = base64.b64encode(file_content).decode('utf-8')
                admin_profile.avatar_filename = avatar_file.name
                admin_profile.avatar_content_type = avatar_file.content_type

            user.save()
            admin_profile.save()

            return Response({
                "success": True,
                "entity": "admin",
                "message": "Profile updated successfully",
                "data": {
                    "id": user.id,
                    "user_id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "full_name": f"{user.first_name} {user.last_name}".strip() or user.username,
                    "phone": admin_profile.phone,
                    "user_type": "admin",
                    "avatar": admin_profile.avatar,
                }
            })

        # Admin updating another user — try Client first, then CustomUser
        try:
            client = Client.objects.get(pk=pk)
            serializer = ClientCreateUpdateSerializer(
                client, data=request.data, partial=True, context={'request': request}
            )
            if serializer.is_valid():
                client = serializer.save()
                return Response({
                    "success": True,
                    "entity": "client",
                    "message": "Client updated successfully",
                    "data": ClientSerializer(client).data
                })
            return Response({
                "success": False,
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        except Client.DoesNotExist:
            pass

        # Try CustomUser
        try:
            custom_user = CustomUser.objects.get(pk=pk)
            serializer = CustomUserCreateUpdateSerializer(
                custom_user, data=request.data, partial=True, context={'request': request}
            )
            if serializer.is_valid():
                user_obj = serializer.save()
                return Response({
                    "success": True,
                    "entity": "user",
                    "message": "User updated successfully",
                    "data": CustomUserSerializer(user_obj).data
                })
            return Response({
                "success": False,
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        except CustomUser.DoesNotExist:
            return Response({
                "success": False,
                "message": f"No user or client found with ID {pk}"
            }, status=status.HTTP_404_NOT_FOUND)

    # ================= CLIENT =================
    elif hasattr(user, 'client_profile'):
        client = user.client_profile

        # Check if client is updating their own profile
        if str(client.id) == str(pk):
            serializer = ClientCreateUpdateSerializer(
                client, data=request.data, partial=True, context={'request': request}
            )
            if serializer.is_valid():
                client = serializer.save()
                return Response({
                    "success": True,
                    "entity": "client",
                    "message": "Profile updated successfully",
                    "data": ClientSerializer(client).data
                })
            return Response({
                "success": False,
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if client is updating one of their created users
        try:
            custom_user = CustomUser.objects.get(pk=pk, created_by=client.auth_user)
            serializer = CustomUserCreateUpdateSerializer(
                custom_user, data=request.data, partial=True, context={'request': request}
            )
            if serializer.is_valid():
                user_obj = serializer.save()
                return Response({
                    "success": True,
                    "entity": "user",
                    "message": "User updated successfully",
                    "data": CustomUserSerializer(user_obj).data
                })
            return Response({
                "success": False,
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        except CustomUser.DoesNotExist:
            return Response({
                "success": False,
                "message": "User not found or you don't have permission to update this user"
            }, status=status.HTTP_404_NOT_FOUND)

    # ================= CUSTOM USER =================
    else:
        try:
            custom_user = CustomUser.objects.get(auth_user=user)

            # Verify the pk matches
            if str(custom_user.id) != str(pk):
                return Response({
                    "success": False,
                    "message": "You can only update your own profile"
                }, status=status.HTTP_403_FORBIDDEN)

            serializer = CustomUserCreateUpdateSerializer(
                custom_user, data=request.data, partial=True, context={'request': request}
            )
            if serializer.is_valid():
                user_obj = serializer.save()
                return Response({
                    "success": True,
                    "entity": "user",
                    "message": "Profile updated successfully",
                    "data": CustomUserSerializer(user_obj).data
                })
            return Response({
                "success": False,
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        except CustomUser.DoesNotExist:
            return Response({
                "success": False,
                "message": "User profile not found"
            }, status=status.HTTP_404_NOT_FOUND)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def account_delete(request, pk):
    user = request.user

    # ================= ADMIN =================
    if user.is_superuser:
        # Try CLIENT
        client = Client.objects.filter(pk=pk).first()
        if client:
            if client.auth_user == user:
                return Response({
                    "success": False,
                    "message": "You cannot delete your own account"
                }, status=status.HTTP_400_BAD_REQUEST)

            client.auth_user.delete()
            return Response({
                "success": True,
                "entity": "client",
                "message": "Client deleted successfully"
            }, status=status.HTTP_200_OK)

        # Try USER
        custom_user = CustomUser.objects.filter(pk=pk).first()
        if not custom_user:
            return Response({
                "success": False,
                "message": "Account not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if custom_user.auth_user == user:
            return Response({
                "success": False,
                "message": "You cannot delete your own account"
            }, status=status.HTTP_400_BAD_REQUEST)

        custom_user.auth_user.delete()
        return Response({
            "success": True,
            "entity": "user",
            "message": "User deleted successfully"
        }, status=status.HTTP_200_OK)

    # ================= CLIENT =================
    if hasattr(user, 'client_profile'):
        custom_user = CustomUser.objects.filter(
            pk=pk,
            client=user.client_profile
        ).first()

        if not custom_user:
            return Response({
                "success": False,
                "message": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if custom_user.auth_user == user:
            return Response({
                "success": False,
                "message": "You cannot delete your own account"
            }, status=status.HTTP_400_BAD_REQUEST)

        custom_user.auth_user.delete()
        return Response({
            "success": True,
            "entity": "user",
            "message": "User deleted successfully"
        }, status=status.HTTP_200_OK)

    return Response({
        "success": False,
        "message": "You do not have permission"
    }, status=status.HTTP_403_FORBIDDEN)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def account_detail(request, pk):
    """
    Unified wrapper for:
    - Admin   -> client_detail
    - Client  -> user_detail
    """

    django_request = request._request  # ✅ important

    # ================= ADMIN =================
    if request.user.is_superuser:
        return client_detail(django_request, pk)

    # ================= CLIENT =================
    if hasattr(request.user, 'client_profile'):
        return user_detail(django_request, pk)

    return Response({
        "success": False,
        "message": "You do not have permission to view this account"
    }, status=status.HTTP_403_FORBIDDEN)


# ================ CLIENT DETAIL VIEW ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_detail(request, pk):
    """Get single client details"""
    client = get_object_or_404(Client.objects.select_related('auth_user', 'created_by', 'language'),
                               pk=pk)

    if not (request.user.is_superuser or request.user == client.auth_user):
        return Response({
            "success": False,
            "message": "You do not have permission to view this client"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = ClientSerializer(client)
    return Response({
        "success": True,
        "message": "Client retrieved successfully",
        "data": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_detail(request, pk):
    """Get single custom user details"""
    custom_user = get_object_or_404(
        CustomUser.objects.select_related('auth_user', 'client', 'created_by', 'language'), pk=pk)

    if hasattr(request.user, 'client_profile'):
        if custom_user.client != request.user.client_profile:
            return Response({
                "success": False,
                "message": "You do not have permission to view this user"
            }, status=status.HTTP_403_FORBIDDEN)
    elif not (request.user.is_superuser or request.user == custom_user.auth_user):
        return Response({
            "success": False,
            "message": "You do not have permission to view this user"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = CustomUserSerializer(custom_user)
    return Response({
        "success": True,
        "message": "User retrieved successfully",
        "data": serializer.data
    })


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def account_toggle_active(request, pk):
    auth_user = request.user
    is_active = request.data.get('is_active')

    # ================= VALIDATE is_active =================
    if is_active is None:
        return Response({
            "success": False,
            "message": "is_active is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(is_active, bool):
        return Response({
            "success": False,
            "message": "is_active must be a boolean value (true or false)"
        }, status=status.HTTP_400_BAD_REQUEST)

    # ================= ADMIN =================
    if auth_user.is_superuser:

        # Try CLIENT first
        client = Client.objects.select_related('auth_user').filter(pk=pk).first()
        if client:
            if client.auth_user == auth_user:
                return Response({
                    "success": False,
                    "message": "You cannot change your own account status"
                }, status=status.HTTP_400_BAD_REQUEST)

            client.is_active = is_active
            client.auth_user.is_active = is_active
            client.save()
            client.auth_user.save()

            status_label = "activated" if is_active else "deactivated"
            return Response({
                "success": True,
                "entity": "client",
                "message": f"Client {status_label} successfully",
                "data": {
                    "id": client.id,
                    "username": client.auth_user.username,
                    "is_active": is_active
                }
            })

        # Try USER
        custom_user = CustomUser.objects.select_related('auth_user').filter(pk=pk).first()
        if not custom_user:
            return Response({
                "success": False,
                "message": "Account not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if custom_user.auth_user == auth_user:
            return Response({
                "success": False,
                "message": "You cannot change your own account status"
            }, status=status.HTTP_400_BAD_REQUEST)

        custom_user.is_active = is_active
        custom_user.auth_user.is_active = is_active
        custom_user.save()
        custom_user.auth_user.save()

        status_label = "activated" if is_active else "deactivated"
        return Response({
            "success": True,
            "entity": "user",
            "message": f"User {status_label} successfully",
            "data": {
                "id": custom_user.id,
                "username": custom_user.auth_user.username,
                "is_active": is_active
            }
        })

    # ================= CLIENT =================
    if hasattr(auth_user, 'client_profile'):
        custom_user = CustomUser.objects.select_related('auth_user').filter(
            pk=pk,
            client=auth_user.client_profile
        ).first()

        if not custom_user:
            return Response({
                "success": False,
                "message": "User not found or does not belong to your client"
            }, status=status.HTTP_404_NOT_FOUND)

        if custom_user.auth_user == auth_user:
            return Response({
                "success": False,
                "message": "You cannot change your own account status"
            }, status=status.HTTP_400_BAD_REQUEST)

        custom_user.is_active = is_active
        custom_user.auth_user.is_active = is_active
        custom_user.save()
        custom_user.auth_user.save()

        status_label = "activated" if is_active else "deactivated"
        return Response({
            "success": True,
            "entity": "user",
            "message": f"User {status_label} successfully",
            "data": {
                "id": custom_user.id,
                "username": custom_user.auth_user.username,
                "is_active": is_active
            }
        })

    # ================= FALLBACK =================
    return Response({
        "success": False,
        "message": "You do not have permission to perform this action"
    }, status=status.HTTP_403_FORBIDDEN)


# ================ CHANGE PASSWORD VIEW ================

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def change_password(request, pk, user_type):
    """Change password for client or custom user"""
    if user_type == 'client':
        user_obj = get_object_or_404(Client, pk=pk)
    elif user_type == 'user':
        user_obj = get_object_or_404(CustomUser, pk=pk)
    else:
        return Response({
            "success": False,
            "message": "Invalid user type"
        }, status=status.HTTP_400_BAD_REQUEST)

    auth_user = user_obj.auth_user

    if not (request.user.is_superuser or request.user == auth_user):
        return Response({
            "success": False,
            "message": "You can only change your own password"
        }, status=status.HTTP_403_FORBIDDEN)

    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')

    if not new_password:
        return Response({
            "success": False,
            "message": "New password is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({
            "success": False,
            "message": "Passwords do not match"
        }, status=status.HTTP_400_BAD_REQUEST)

    if request.user.is_superuser and request.user != auth_user:
        auth_user.set_password(new_password)
    else:
        if not old_password:
            return Response({
                "success": False,
                "message": "Old password is required"
            }, status=status.HTTP_400_BAD_REQUEST)

        if not auth_user.check_password(old_password):
            return Response({
                "success": False,
                "message": "Old password is incorrect"
            }, status=status.HTTP_400_BAD_REQUEST)
        auth_user.set_password(new_password)

    auth_user.save()
    return Response({
        "success": True,
        "message": "Password changed successfully"
    })


# ================ HELPER: Build client response data ================

def build_client_data(client):
    """Build client response data dict without serializer"""
    return {
        "id": client.id,
        "username": client.auth_user.username,
        "email": client.auth_user.email,
        "first_name": client.auth_user.first_name,
        "last_name": client.auth_user.last_name,
        "is_active": client.auth_user.is_active,
        "company_name": getattr(client, 'company_name', None),
    }


def send_password_reset_email_via_sqlserver(email, reset_link, user_name):
    """
    Send password reset email using SQL Server Database Mail with beautiful HTML template
    """
    try:
        import pyodbc
        from django.conf import settings

        # SQL Server connection details
        connection_string = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={settings.SQL_SERVER_HOST};"
            f"DATABASE=msdb;"
            f"UID={settings.SQL_SERVER_USER};"
            f"PWD={settings.SQL_SERVER_PASSWORD};"
        )

        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        # Beautiful HTML email body
        email_body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Password Reset - MediPro</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 40px 0;">
        <tr>
            <td align="center">
                <!-- Main Container -->
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); overflow: hidden;">

                    <!-- Header with Gradient -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #00897B 0%, #004D40 100%); padding: 40px 30px; text-align: center;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: 700; letter-spacing: -0.5px;">
                                🔐 Password Reset Request
                            </h1>
                            <p style="margin: 10px 0 0 0; color: #B2DFDB; font-size: 14px;">
                                MediPro Security
                            </p>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <!-- Greeting -->
                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #1F2937; line-height: 1.6;">
                                Hello <strong>{user_name}</strong>,
                            </p>

                            <!-- Message -->
                            <p style="margin: 0 0 25px 0; font-size: 15px; color: #4B5563; line-height: 1.6;">
                                We received a request to reset the password for your MediPro account. If you didn't make this request, you can safely ignore this email.
                            </p>

                            <!-- Reset Button -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center" style="padding: 20px 0;">
                                        <a href="{reset_link}" style="display: inline-block; background: linear-gradient(135deg, #00897B 0%, #00695C 100%); color: #ffffff; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(0, 137, 123, 0.3); transition: all 0.3s ease;">
                                            Reset My Password
                                        </a>
                                    </td>
                                </tr>
                            </table>

                            <!-- Alternative Link -->
                            <p style="margin: 25px 0 0 0; font-size: 13px; color: #6B7280; line-height: 1.6;">
                                If the button doesn't work, copy and paste this link into your browser:
                            </p>
                            <p style="margin: 10px 0 0 0; padding: 12px; background-color: #F3F4F6; border-radius: 6px; word-break: break-all;">
                                <a href="{reset_link}" style="color: #00897B; text-decoration: none; font-size: 13px;">
                                    {reset_link}
                                </a>
                            </p>
                        </td>
                    </tr>

                    <!-- Info Box -->
                    <tr>
                        <td style="padding: 0 30px 40px 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%); border-left: 4px solid #3B82F6; border-radius: 8px;">
                                <tr>
                                    <td style="padding: 20px;">
                                        <p style="margin: 0 0 10px 0; font-size: 14px; color: #1E40AF; font-weight: 600;">
                                            ⏰ Important Security Information
                                        </p>
                                        <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #1E3A8A; line-height: 1.8;">
                                            <li>This link will expire in <strong>24 hours</strong></li>
                                            <li>For security, this link can only be used once</li>
                                            <li>If you didn't request this reset, please ignore this email</li>
                                        </ul>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #F9FAFB; padding: 30px; border-top: 1px solid #E5E7EB;">
                            <p style="margin: 0 0 10px 0; font-size: 13px; color: #6B7280; text-align: center; line-height: 1.6;">
                                This is an automated email from MediPro. Please do not reply to this message.
                            </p>
                            <p style="margin: 0; font-size: 13px; color: #9CA3AF; text-align: center;">
                                © 2026 MediPro. All rights reserved.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 20px;">
                                <tr>
                                    <td align="center">
                                        <p style="margin: 0; font-size: 12px; color: #9CA3AF;">
                                            Need help? Contact us at 
                                            <a href="mailto:support@medipro.com" style="color: #00897B; text-decoration: none;">
                                                support@medipro.com
                                            </a>
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>

                <!-- Spacer -->
                <table width="600" cellpadding="0" cellspacing="0">
                    <tr>
                        <td height="20"></td>
                    </tr>
                </table>

            </td>
        </tr>
    </table>
</body>
</html>
        """

        # Execute sp_send_dbmail with HTML format
        sql = """
        EXEC msdb.dbo.sp_send_dbmail 
            @profile_name = 'SSIS_Mail_Profile',
            @recipients = ?,
            @subject = 'Reset Your MediPro Password',
            @body = ?,
            @body_format = 'HTML'
        """

        cursor.execute(sql, (email, email_body))
        conn.commit()
        cursor.close()
        conn.close()

        return True, "Email sent successfully"

    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request(request):
    """
    Request password reset for any user type (Admin, Client, or CustomUser)
    Accepts email and sends reset link
    """
    email = request.data.get('email')

    if not email:
        return Response({
            "success": False,
            "message": "Email is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Find user by email
        user = User.objects.get(email=email)

        # Determine user type and get display name
        user_name = user.username
        user_type = "user"

        if user.is_superuser:
            if hasattr(user, 'admin_profile'):
                user_name = f"{user.first_name} {user.last_name}".strip() or user.username
            user_type = "admin"
        elif hasattr(user, 'client_profile'):
            client = user.client_profile
            user_name = f"{client.first_name} {client.last_name}".strip() or user.username
            user_type = "client"
        else:
            try:
                from .models import CustomUser  # Adjust import based on your project structure
                custom_user = CustomUser.objects.get(auth_user=user)
                user_name = f"{custom_user.first_name} {custom_user.last_name}".strip() or user.username
                user_type = "custom_user"
            except:
                pass

        # Generate password reset token
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Build reset link - adjust frontend URL as needed
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        reset_link = f"{frontend_url}/password-reset/{uid}/{token}/"

        # Send email via SQL Server Database Mail
        success, message = send_password_reset_email_via_sqlserver(
            email=email,
            reset_link=reset_link,
            user_name=user_name
        )

        if success:
            return Response({
                "success": True,
                "message": "Password reset link has been sent to your email",
                "user_type": user_type
            })
        else:
            return Response({
                "success": False,
                "message": message
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except User.DoesNotExist:
        # For security, don't reveal if email exists or not
        return Response({
            "success": True,
            "message": "If an account exists with this email, a password reset link has been sent"
        })
    except Exception as e:
        return Response({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    """
    Confirm password reset with token
    Accepts: uidb64, token, new_password
    """
    uidb64 = request.data.get('uid')
    token = request.data.get('token')
    new_password = request.data.get('new_password')

    if not all([uidb64, token, new_password]):
        return Response({
            "success": False,
            "message": "UID, token, and new password are required"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Decode user ID
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)

        # Verify token
        if not default_token_generator.check_token(user, token):
            return Response({
                "success": False,
                "message": "Invalid or expired reset link"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate password strength (optional - add your own validation)
        if len(new_password) < 8:
            return Response({
                "success": False,
                "message": "Password must be at least 8 characters long"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Set new password
        user.set_password(new_password)
        user.save()

        return Response({
            "success": True,
            "message": "Password has been reset successfully"
        })

    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({
            "success": False,
            "message": "Invalid reset link"
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_validate_token(request):
    """
    Validate if reset token is still valid
    Accepts: uidb64, token
    """
    uidb64 = request.data.get('uid')
    token = request.data.get('token')

    if not all([uidb64, token]):
        return Response({
            "success": False,
            "message": "UID and token are required"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)

        if default_token_generator.check_token(user, token):
            return Response({
                "success": True,
                "message": "Token is valid",
                "email": user.email
            })
        else:
            return Response({
                "success": False,
                "message": "Invalid or expired token"
            }, status=status.HTTP_400_BAD_REQUEST)

    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({
            "success": False,
            "message": "Invalid token"
        }, status=status.HTTP_400_BAD_REQUEST)


class ClientsAndUsersListAPIView(APIView):
    """
    Simple API to fetch list of all clients and their users.
    Returns clients array with their users nested inside.
    """

    def get(self, request):
        # Get all active clients with their auth_user data
        clients = Client.objects.filter(is_active=True).select_related('auth_user').prefetch_related(
            'users__auth_user'  # Prefetch users and their auth_user data
        ).order_by('-created_at')

        result = []

        for client in clients:
            # Client data
            client_data = {
                'id': client.id,
                'name': client.auth_user.get_full_name() or client.auth_user.username or client.company_name,
                'username': client.auth_user.username,
                'email': client.auth_user.email,
                'first_name': client.auth_user.first_name,
                'last_name': client.auth_user.last_name,
                'company_name': client.company_name,
                'phone': client.phone,
                'is_active': client.is_active,
                'avatar': client.avatar,  # Uses the property from model
                'users': []
            }

            # Add users for this client
            for user in client.users.filter(is_active=True).select_related('auth_user'):
                user_data = {
                    'id': user.auth_user.id,
                    'name': user.auth_user.get_full_name() or user.auth_user.username,
                    'username': user.auth_user.username,
                    'email': user.auth_user.email,
                    'first_name': user.auth_user.first_name,
                    'last_name': user.auth_user.last_name,
                    'phone': user.phone,
                    'is_active': user.is_active,
                    'avatar': user.avatar,  # Uses the property from model
                }
                client_data['users'].append(user_data)

            # Only add clients that have at least one user (optional)
            # Remove this condition if you want to show clients with 0 users
            if client_data['users']:
                result.append(client_data)

        return Response({
            'success': True,
            'count': len(result),
            'data': result
        }, status=status.HTTP_200_OK)
