from rest_framework import serializers
from .models import Module, UserModule
from django.contrib.auth import get_user_model

User = get_user_model()

class ModuleSerializer(serializers.ModelSerializer):
    """
    Full module serializer (flat — no hierarchy on Module itself).
    Hierarchy lives exclusively on UserModule.parent_id.
    """

    class Meta:
        model  = Module
        fields = ['id', 'code', 'description', 'url', 'icon', 'is_active']
        read_only_fields = ['id']


class ModuleFlatSerializer(serializers.ModelSerializer):
    """
    Flat list — used by the /api/modules/list endpoint.
    No parent_id here; the per-user hierarchy is on UserModule.parent_id.
    """

    class Meta:
        model  = Module
        fields = ['id', 'code', 'description', 'url', 'icon', 'is_active']
        read_only_fields = ['id']


class UserModuleSerializer(serializers.ModelSerializer):
    module_code        = serializers.CharField(source='module.code',        read_only=True)
    module_description = serializers.CharField(source='module.description', read_only=True)
    module_url         = serializers.CharField(source='module.url',         read_only=True)
    module_icon        = serializers.CharField(source='module.icon',        read_only=True)
    # module_parent_id comes from UserModule.parent_id — the per-user hierarchy
    module_parent_id   = serializers.IntegerField(
        source='parent_id', read_only=True, allow_null=True,
    )
    username = serializers.CharField(source='user.username', read_only=True)
    email    = serializers.CharField(source='user.email',    read_only=True)

    class Meta:
        model  = UserModule
        fields = [
            'id', 'user', 'username', 'email',
            'module', 'module_code', 'module_description',
            'module_url', 'module_icon', 'module_parent_id',
            'is_active', 'is_default', 'sequence', 'parent_id',
        ]
        read_only_fields = ['id']


class UserModuleCreateSerializer(serializers.Serializer):
    user_id   = serializers.IntegerField()
    module_id = serializers.IntegerField()
    is_active = serializers.BooleanField(default=True)

    def validate(self, data):
        if not User.objects.filter(id=data['user_id']).exists():
            raise serializers.ValidationError({'user_id': 'User does not exist.'})
        if not Module.objects.filter(id=data['module_id'], is_active=True).exists():
            raise serializers.ValidationError({'module_id': 'Module does not exist or is inactive.'})
        if UserModule.objects.filter(user_id=data['user_id'], module_id=data['module_id']).exists():
            raise serializers.ValidationError('This module is already assigned to the user.')
        return data

    def create(self, validated_data):
        return UserModule.objects.create(**validated_data)


class UserModuleBulkAssignSerializer(serializers.Serializer):
    """
    Bulk-assign modules to a user with per-user hierarchy.

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

    parent_id in each module item is the per-user parent stored on UserModule.
    """
    target_id  = serializers.IntegerField()
    modules    = serializers.ListField(
        child=serializers.DictField(), min_length=1,
        help_text='List of {module_id, parent_id, sequence, roles} objects',
    )
    is_active  = serializers.BooleanField(default=True)
    is_default = serializers.BooleanField(default=False)

    def validate_target_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError('User does not exist.')
        return value

    def validate_modules(self, value):
        """Validate each module item and verify all module_ids exist and are active."""
        validated  = []
        module_ids = []

        for item in value:
            module_id = item.get('module_id')
            parent_id = item.get('parent_id', None)
            sequence  = item.get('sequence', 0)

            if module_id is None:
                raise serializers.ValidationError('Each item must have a module_id.')
            if not isinstance(module_id, int):
                raise serializers.ValidationError(f'module_id must be an integer, got: {module_id}')
            if parent_id is not None and not isinstance(parent_id, int):
                raise serializers.ValidationError(
                    f'parent_id must be an integer or null, got: {parent_id}'
                )

            module_ids.append(module_id)
            validated.append({
                'module_id': module_id,
                'parent_id': parent_id,
                'sequence': sequence,
            })

        # Verify all module_ids exist and are active
        existing_ids = set(
            Module.objects.filter(id__in=module_ids, is_active=True).values_list('id', flat=True)
        )
        invalid = set(module_ids) - existing_ids
        if invalid:
            raise serializers.ValidationError(f'Invalid or inactive module IDs: {sorted(invalid)}')

        # Validate parent_ids reference active modules
        all_valid_ids = set(Module.objects.filter(is_active=True).values_list('id', flat=True))
        for item in validated:
            pid = item['parent_id']
            if pid is not None and pid not in all_valid_ids:
                raise serializers.ValidationError(
                    f"parent_id={pid} for module_id={item['module_id']} does not exist or is inactive."
                )

        return validated

    def create(self, validated_data):
        target_id  = validated_data['target_id']
        modules    = validated_data['modules']
        is_active  = validated_data['is_active']
        is_default = validated_data['is_default']

        batch_ids           = {item['module_id'] for item in modules}
        already_assigned_ids = set(
            UserModule.objects.filter(user_id=target_id).values_list('module_id', flat=True)
        )

        created_list, updated_list, errors = [], [], []

        for item in modules:
            module_id = item['module_id']
            parent_id = item['parent_id']
            sequence  = item['sequence']

            if parent_id is not None:
                if parent_id not in batch_ids and parent_id not in already_assigned_ids:
                    errors.append({
                        'module_id': module_id,
                        'error': (
                            f'parent_id={parent_id} is not assigned to this user. '
                            'Assign the parent module first.'
                        ),
                    })
                    continue
                if parent_id == module_id:
                    errors.append({'module_id': module_id, 'error': 'A module cannot be its own parent.'})
                    continue

            try:
                obj, created = UserModule.objects.update_or_create(
                    user_id=target_id,
                    module_id=module_id,
                    defaults={
                        'parent_id':  parent_id,
                        'sequence':   sequence,
                        'is_active':  is_active,
                        'is_default': is_default,
                    },
                )
                (created_list if created else updated_list).append(module_id)
            except Exception as e:
                errors.append({'module_id': module_id, 'error': str(e)})

        if errors:
            raise serializers.ValidationError({'module_errors': errors})

        return created_list, updated_list


class UserModuleListSerializer(serializers.Serializer):
    """
    Read-only flat serializer for listing assigned modules.
    parent_id = UserModule.parent_id (per-user hierarchy).
    """
    id          = serializers.IntegerField()
    code        = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    url         = serializers.CharField(allow_null=True)
    icon        = serializers.CharField(allow_null=True)
    is_active   = serializers.BooleanField()
    parent_id   = serializers.IntegerField(allow_null=True)   # UserModule.parent_id


class HierarchyUpdateItemSerializer(serializers.Serializer):
    """A single item in a bulk hierarchy update."""
    module_id = serializers.IntegerField()
    parent_id = serializers.IntegerField(allow_null=True)
    sequence  = serializers.IntegerField(default=0)


class BulkHierarchyUpdateSerializer(serializers.Serializer):
    """
    Bulk update hierarchy for already-assigned modules.
    PATCH /api/modules/assign/hierarchy/
    {
        "target_id": 5,
        "hierarchy": [
            { "module_id": 1,  "parent_id": null, "sequence": 1 },
            { "module_id": 20, "parent_id": null, "sequence": 2 },
            { "module_id": 6,  "parent_id": 20,   "sequence": 3 }
        ]
    }
    """
    target_id = serializers.IntegerField()
    hierarchy = HierarchyUpdateItemSerializer(many=True, min_length=1)

    def validate_target_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError('User does not exist.')
        return value

    def validate(self, data):
        target_id  = data['target_id']
        module_ids = [item['module_id'] for item in data['hierarchy']]

        assigned_ids = set(
            UserModule.objects.filter(user_id=target_id, module_id__in=module_ids)
            .values_list('module_id', flat=True)
        )
        not_assigned = set(module_ids) - assigned_ids
        if not_assigned:
            raise serializers.ValidationError({
                'hierarchy': f'Module IDs not assigned to this user: {sorted(not_assigned)}'
            })
        return data