from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from EduraAPI.apps.users.models import CustomUser

from .models import Module, UserModule
from .serializers import (
    ModuleFlatSerializer,
    UserModuleBulkAssignSerializer,
    BulkHierarchyUpdateSerializer,
)

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_client_profile(user):
    return getattr(user, 'client_profile', None)


def _check_client_owns_target(client_profile, target_id):
    from EduraAPI.apps.users.models import CustomUser
    return CustomUser.objects.filter(auth_user_id=target_id, client=client_profile).exists()


def _serialize_user_module(um):
    """
    Serialize a single UserModule instance.
    module_parent_id = UserModule.parent_id (per-user hierarchy).
    """
    return {
        'id':               um.id,
        'user_id':          um.user_id,
        'module_id':        um.module_id,
        'module_name':      um.module.description or um.module.code,
        'module_code':      um.module.code,
        'module_parent_id': um.parent_id,   # UserModule.parent_id — per-user hierarchy
        'is_active':        um.is_active,
        'is_default':       um.is_default,
        'sequence':         um.sequence,
        'roles':            [],
        'show_in_sidebar':  um.show_in_sidebar,
    }


def _serialize_user_modules(queryset):
    return [_serialize_user_module(um) for um in queryset]


def _build_module_tree(flat_modules):
    """
    Convert a flat list of module dicts (each with 'id' and 'parent_id') into
    a nested parent→children tree suitable for the sidebar.

    Each item must have at least: id, code, description, url, icon, is_active,
    parent_id (from user_modules.parent_id), sequence, is_default, show_in_sidebar.

    Returns a list of root-level modules with a 'children' key on each.
    Orphan modules (parent_id set but parent not in list) are promoted to root.
    """
    by_id = {m['id']: dict(m, children=[]) for m in flat_modules}

    roots = []
    for m in by_id.values():
        pid = m.get('parent_id')
        if pid and pid in by_id:
            by_id[pid]['children'].append(m)
        else:
            # No parent_id, or parent not in assigned list → treat as root
            m['parent_id'] = None
            roots.append(m)

    # Sort roots and children by sequence
    roots.sort(key=lambda x: (x.get('sequence') or 999, x['id']))
    for m in by_id.values():
        m['children'].sort(key=lambda x: (x.get('sequence') or 999, x['id']))

    return roots


# ─────────────────────────────────────────────────────────────────────────────
# MODULE LIST VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class ModuleListView(APIView):
    """
    GET /api/modules/list
    Flat list of all active modules (no hierarchy — hierarchy is per-user on UserModule).
    Used by the assignment modal step-1 picker.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        auth_user = request.user
        if auth_user.is_superuser:
            modules = Module.objects.filter(is_active=True).order_by('id')
        elif _get_client_profile(auth_user):
            assigned_module_ids = UserModule.objects.filter(
                user_id=auth_user.id,
                is_active=True,
                module__is_active=True,
            ).values_list('module_id', flat=True)
            modules = Module.objects.filter(id__in=assigned_module_ids, is_active=True).order_by('id')
        else:
            modules = Module.objects.none()
        serializer = ModuleFlatSerializer(modules, many=True)
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
# USER MODULE VIEWS
# ─────────────────────────────────────────────────────────────────────────────

class UserModulesAPIView(APIView):
    """
    GET /api/modules/user/<user_id>/
    Active modules assigned to the given user (flat list).
    module_parent_id = UserModule.parent_id (per-user hierarchy).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id=None):
        if user_id is None:
            user_id = request.user.id
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found'}, status=404)

        if not (request.user.id == user_id or request.user.is_staff):
            return Response({'success': False, 'error': 'Permission denied'}, status=403)

        user_modules = (
            UserModule.objects
            .filter(user_id=user_id, is_active=True, module__is_active=True)
            .select_related('module')
            .order_by('sequence', 'module__id')
        )
        modules_list = _serialize_user_modules(user_modules)
        return Response({
            'success': True, 'user_id': user_id,
            'username': user.username, 'email': user.email,
            'modules': modules_list, 'count': len(modules_list),
        })


class CurrentUserModulesAPIView(APIView):
    """
    GET /api/modules/my-modules/

    Returns the logged-in user's assigned modules as a NESTED TREE built from
    UserModule.parent_id (per-user hierarchy).

    Response shape:
    {
        "success": true,
        "user_id": 5,
        "username": "john",
        "email": "john@example.com",
        "modules": [
            {
                "id": 20, "code": "REPORTS", "description": "Reports", ...
                "parent_id": null,
                "show_in_sidebar": true,
                "children": [
                    { "id": 6, "code": "SALES_RPT", "parent_id": 20, "show_in_sidebar": true, "children": [] },
                    ...
                ]
            },
            ...
        ],
        "count": <total flat count>
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.id

        # Fetch only from user_modules JOIN modules — never expose modules not assigned to this user
        user_modules = (
            UserModule.objects
            .filter(user_id=user_id, is_active=True, module__is_active=True)
            .select_related('module')
            .order_by('sequence', 'module__id')
        )

        flat = [
            {
                'id':         um.module_id,
                'code':       um.module.code,
                'description': um.module.description,
                'url':        um.module.url,
                'icon':       um.module.icon,
                'is_active':  um.is_active,
                'parent_id':  um.parent_id,   # UserModule.parent_id — per-user hierarchy
                'is_default': um.is_default,
                'sequence':   um.sequence,
                'show_in_sidebar': um.show_in_sidebar,
                'roles':      [],
            }
            for um in user_modules
        ]

        tree = _build_module_tree(flat)

        return Response({
            'success':  True,
            'user_id':  user_id,
            'username': request.user.username,
            'email':    request.user.email,
            'modules':  tree,
            'count':    len(flat),
        })


class CheckModuleAccessAPIView(APIView):
    """GET /api/modules/check/<module_code>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, module_code):
        try:
            module = Module.objects.get(code=module_code, is_active=True)
        except Module.DoesNotExist:
            return Response(
                {'success': False, 'has_access': False, 'error': 'Module not found or inactive'},
                status=404,
            )

        try:
            um             = UserModule.objects.get(user_id=request.user.id, module_id=module.id, is_active=True)
            has_access     = True
            user_parent_id = um.parent_id   # per-user hierarchy
        except UserModule.DoesNotExist:
            has_access     = False
            user_parent_id = None

        return Response({
            'success':          True,
            'has_access':       has_access,
            'module_code':      module_code,
            'module_id':        module.id,
            'module_icon':      module.icon,
            'module_parent_id': user_parent_id,
            'user_id':          request.user.id,
        })


class ModuleIconListAPIView(APIView):
    """GET /api/modules/icons/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        icons = (
            Module.objects.filter(is_active=True)
            .exclude(icon__isnull=True).exclude(icon='')
            .values_list('icon', flat=True).distinct()
        )
        return Response({'success': True, 'icons': list(icons), 'count': len(icons)})


class UpdateModuleSequenceAPIView(APIView):
    """POST /api/modules/update-sequence/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        if isinstance(data, dict):
            data = [data]
        elif not isinstance(data, list):
            return Response(
                {'success': False, 'error': 'Request must be an object or array of objects'},
                status=400,
            )
        return self._update_sequences(request.user, data)

    def _update_sequences(self, request_user, updates):
        try:
            results = []
            with transaction.atomic():
                for update in updates:
                    user_id   = update.get('user_id')
                    module_id = update.get('module_id')
                    sequence  = update.get('sequence')
                    if user_id is None or module_id is None or sequence is None:
                        raise ValueError('user_id, module_id, and sequence are required')
                    if not isinstance(sequence, int) or sequence < 0:
                        raise ValueError('Sequence must be a non-negative integer')
                    try:
                        um = UserModule.objects.get(user_id=user_id, module_id=module_id, is_active=True)
                    except UserModule.DoesNotExist:
                        raise ValueError(f'Module {module_id} not found or not active for user {user_id}')
                    old_seq     = um.sequence
                    um.sequence = sequence
                    um.save()
                    results.append({
                        'user_id': user_id, 'module_id': module_id,
                        'old_sequence': old_seq, 'new_sequence': sequence,
                        'user_module_id': um.id, 'module_code': um.module.code,
                    })
            return Response({'success': True, 'message': f'Updated {len(results)} module(s)', 'data': results})
        except (ValueError, PermissionError) as e:
            return Response({'success': False, 'error': str(e)}, status=400)
        except Exception as e:
            return Response({'success': False, 'error': f'Server error: {str(e)}'}, status=500)


class UpdateModuleSideBarVisibilityAPIView(APIView):
    """
    POST /api/modules/batch-update-visibility/

    Payload:
    {
        "hide_modules": [1, 2, 3],
        "unhide_modules": [4, 5, 6]
    }

    Updates show_in_sidebar field for multiple modules in a single transaction.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        hide_modules = request.data.get('hide_modules', [])
        unhide_modules = request.data.get('unhide_modules', [])

        if not isinstance(hide_modules, list):
            return Response(
                {'success': False, 'error': 'hide_modules must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(unhide_modules, list):
            return Response(
                {'success': False, 'error': 'unhide_modules must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                updated_count = 0

                # Update modules to hide
                if hide_modules:
                    hidden_count = UserModule.objects.filter(
                        user=user,
                        module_id__in=hide_modules,
                        is_active=True
                    ).update(show_in_sidebar=False)
                    updated_count += hidden_count

                # Update modules to unhide
                if unhide_modules:
                    unhidden_count = UserModule.objects.filter(
                        user=user,
                        module_id__in=unhide_modules,
                        is_active=True
                    ).update(show_in_sidebar=True)
                    updated_count += unhidden_count

                return Response({
                    'success': True,
                    'message': f'Visibility updated for {updated_count} module(s)',
                    'updated_count': updated_count,
                    'hide_modules': hide_modules,
                    'unhide_modules': unhide_modules
                }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to update visibility: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE ASSIGNMENT VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assigned_modules_list(request):
    """
    GET /api/modules/assigned/?target_id=<auth_user_id>

    Returns assigned modules with module_parent_id = UserModule.parent_id
    (the per-user hierarchy).
    """
    auth_user = request.user
    target_id = request.query_params.get('target_id')

    if auth_user.is_superuser:
        if not target_id:
            return Response({'success': False, 'message': 'target_id is required for admin.'}, status=400)
        assigned = (
            UserModule.objects
            .filter(user_id=target_id)
            .select_related('module')
            .order_by('sequence')
        )
        return Response({
            'success': True, 'entity': 'client_modules',
            'message': 'Assigned modules retrieved successfully.',
            'data':    _serialize_user_modules(assigned),
        })

    client = _get_client_profile(auth_user)
    if client:
        if target_id:
            if not _check_client_owns_target(client, target_id):
                return Response({
                    'success': False,
                    'message': 'Target user not found or does not belong to your account.',
                }, status=404)
            assigned = (
                UserModule.objects
                .filter(user_id=target_id)
                .select_related('module')
                .order_by('sequence')
            )
        else:
            assigned = (
                UserModule.objects
                .filter(user_id=auth_user.id)
                .select_related('module')
                .order_by('sequence')
            )

        return Response({
            'success': True, 'entity': 'user_modules',
            'message': 'Assigned modules retrieved successfully.',
            'data':    _serialize_user_modules(assigned),
        })

    return Response({'success': False, 'message': 'Access denied.'}, status=403)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_modules(request):
    """
    POST /api/modules/assign/

    Payload:
    {
        "target_id": 5,
        "modules": [
            { "module_id": 1,  "parent_id": null, "sequence": 1, "roles": [101, 102] },
            { "module_id": 20, "parent_id": null, "sequence": 2, "roles": [] },
            { "module_id": 6,  "parent_id": 20,   "sequence": 3, "roles": [103] }
        ],
        "is_active":  true,
        "is_default": false
    }

    parent_id in each module item is stored on UserModule.parent_id.
    """
    auth_user = request.user
    data      = request.data
    target_id = data.get('target_id')
    print("AUTH USER ID:",auth_user)
    print("TARGET ID:",target_id)

    if not target_id:
        return Response({'success': False, 'message': 'target_id is required.'}, status=400)

    if not auth_user.is_superuser:
        client = _get_client_profile(auth_user)
        if not client:
            return Response({'success': False, 'message': 'Access denied.'}, status=403)
        if not _check_client_owns_target(client, target_id):
            return Response({'success': False, 'message': 'Target user not found.'}, status=404)

        requested_modules = data.get('modules') or []
        requested_module_ids = {
            item.get('module_id')
            for item in requested_modules
            if isinstance(item, dict) and item.get('module_id') is not None
        }
        allowed_module_ids = set(
            UserModule.objects.filter(
                user_id=auth_user.id,
                is_active=True,
                module__is_active=True,
            ).values_list('module_id', flat=True)
        )
        disallowed_module_ids = sorted(
            module_id for module_id in requested_module_ids if module_id not in allowed_module_ids
        )
        if disallowed_module_ids:
            return Response({
                'success': False,
                'message': (
                    'You can only assign modules already assigned to your client account.'
                ),
                'errors': {'module_ids': disallowed_module_ids},
            }, status=400)

    serializer = UserModuleBulkAssignSerializer(data=data)
    if not serializer.is_valid():
        return Response({'success': False, 'errors': serializer.errors}, status=400)

    try:
        with transaction.atomic():
            created_list, updated_list = serializer.create(serializer.validated_data)

    except Exception as e:
        return Response({'success': False, 'message': f'Assignment failed: {str(e)}'}, status=500)

    return Response({
        'success':  True,
        'message':  'Module assignment processed.',
        'assigned': created_list,
        'updated':  updated_list,
    }, status=201)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def unassign_module(request):
    """
    DELETE /api/modules/unassign/
    { "target_id": <auth_user_id>, "module_id": 3 }
    """
    auth_user = request.user
    target_id = request.data.get('target_id') or request.query_params.get('target_id')
    module_id = request.data.get('module_id') or request.query_params.get('module_id')

    if not target_id or not module_id:
        return Response({'success': False, 'message': 'Both target_id and module_id are required.'}, status=400)

    try:
        target_id = int(target_id)
        module_id = int(module_id)
    except (ValueError, TypeError):
        return Response({'success': False, 'message': 'target_id and module_id must be integers.'}, status=400)

    if not auth_user.is_superuser:
        client = _get_client_profile(auth_user)
        if not client:
            return Response({'success': False, 'message': 'Access denied.'}, status=403)
        if not _check_client_owns_target(client, target_id):
            return Response({
                'success': False,
                'message': 'Target user not found or does not belong to your account.',
            }, status=404)

    # When a parent module is unassigned, promote its children to top-level (parent_id = null)
    with transaction.atomic():
        UserModule.objects.filter(user_id=target_id, parent_id=module_id).update(parent_id=None)
        deleted_count, _ = UserModule.objects.filter(user_id=target_id, module_id=module_id).delete()

    if deleted_count == 0:
        return Response({'success': False, 'message': 'Assignment not found.'}, status=404)
    return Response({'success': True, 'message': 'Module unassigned successfully.'})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_module_assignment(request):
    """
    PATCH /api/modules/assign/update/
    {
        "target_id":  <auth_user_id>,
        "module_id":  3,
        "is_active":  false,
        "is_default": true,
        "sequence":   2,
        "parent_id":  20,          <- optional: update per-user parent
        "show_in_sidebar": false   <- optional: update visibility
    }
    """
    auth_user = request.user
    target_id = request.data.get('target_id') or request.query_params.get('target_id')
    module_id = request.data.get('module_id') or request.query_params.get('module_id')

    if not target_id or not module_id:
        return Response({'success': False, 'message': 'Both target_id and module_id are required.'}, status=400)

    try:
        target_id = int(target_id)
        module_id = int(module_id)
    except (ValueError, TypeError):
        return Response({'success': False, 'message': 'target_id and module_id must be integers.'}, status=400)

    if not auth_user.is_superuser:
        client = _get_client_profile(auth_user)
        if not client:
            return Response({'success': False, 'message': 'Access denied.'}, status=403)
        if not _check_client_owns_target(client, target_id):
            return Response({
                'success': False,
                'message': 'Target user not found or does not belong to your account.',
            }, status=404)

    try:
        assignment = UserModule.objects.get(user_id=target_id, module_id=module_id)
    except UserModule.DoesNotExist:
        return Response({'success': False, 'message': 'Assignment not found.'}, status=404)

    data = request.data

    # Validate parent_id if provided: the parent module must also be assigned to this user
    if 'parent_id' in data and data['parent_id'] is not None:
        parent_module_id = int(data['parent_id'])
        if not UserModule.objects.filter(user_id=target_id, module_id=parent_module_id).exists():
            return Response({
                'success': False,
                'message': f'Parent module (id={parent_module_id}) is not assigned to this user.',
            }, status=400)
        if parent_module_id == module_id:
            return Response({'success': False, 'message': 'A module cannot be its own parent.'}, status=400)

    updatable = ['is_active', 'is_default', 'sequence', 'parent_id', 'show_in_sidebar']
    for field in updatable:
        if field in data:
            setattr(assignment, field, data[field])
    assignment.save(update_fields=[f for f in updatable if f in data])

    assignment.refresh_from_db()

    return Response({
        'success': True,
        'message': 'Assignment updated successfully.',
        'data':    _serialize_user_module(assignment),
    })


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_hierarchy(request):
    """
    PATCH /api/modules/assign/hierarchy/

    Bulk update the entire module tree for a user in one shot.

    Payload:
    {
        "target_id": 5,
        "hierarchy": [
            { "module_id": 1,  "parent_id": null, "sequence": 1 },
            { "module_id": 20, "parent_id": null, "sequence": 2 },
            { "module_id": 6,  "parent_id": 20,   "sequence": 3 }
        ]
    }

    Each item's parent_id is saved to UserModule.parent_id (per-user hierarchy).
    """
    auth_user = request.user
    data      = request.data
    target_id = data.get('target_id')

    if not target_id:
        return Response({'success': False, 'message': 'target_id is required.'}, status=400)

    if not auth_user.is_superuser:
        client = _get_client_profile(auth_user)
        if not client:
            return Response({'success': False, 'message': 'Access denied.'}, status=403)
        if not _check_client_owns_target(client, target_id):
            return Response({
                'success': False,
                'message': 'Target user not found or does not belong to your account.',
            }, status=404)

    serializer = BulkHierarchyUpdateSerializer(data=data)
    if not serializer.is_valid():
        return Response({'success': False, 'errors': serializer.errors}, status=400)

    hierarchy = serializer.validated_data['hierarchy']

    with transaction.atomic():
        updated = []
        for item in hierarchy:
            rows = UserModule.objects.filter(
                user_id=target_id,
                module_id=item['module_id'],
            ).update(
                parent_id=item['parent_id'],
                sequence=item['sequence'],
            )
            if rows:
                updated.append(item['module_id'])

    return Response({
        'success': True,
        'message': f'Hierarchy updated for {len(updated)} module(s).',
        'updated': updated,
    })