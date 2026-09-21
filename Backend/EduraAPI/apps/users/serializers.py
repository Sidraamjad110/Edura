from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import Client, CustomUser, Language, Localization
import base64

User = get_user_model()


# ================ LANGUAGE SERIALIZER ================

class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ['id', 'name', 'code', 'is_active']


# ================ LOCALIZATION SERIALIZERS ================

class LocalizationSerializer(serializers.ModelSerializer):
    language_name = serializers.CharField(source='language.name', read_only=True)
    language_code = serializers.CharField(source='language.code', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Localization
        fields = [
            'id',
            'code',
            'text',
            'language',
            'language_name',
            'language_code',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
            'module_id'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']


# class LocalizationCreateUpdateSerializer(serializers.ModelSerializer):
#     language_code = serializers.CharField(write_only=True)
#
#     class Meta:
#         model = Localization
#         fields = ['code', 'text', 'language_code']
#
#     def validate_language_code(self, value):
#         try:
#             language = Language.objects.get(code=value, is_active=True)
#         except Language.DoesNotExist:
#             raise serializers.ValidationError("Language with this code does not exist or is not active.")
#         return value
#
#     def validate(self, attrs):
#         # Check if localization with same code and language already exists
#         language_code = attrs.get('language_code')
#         code = attrs.get('code')
#
#         if self.instance:  # Update case
#             language = Language.objects.get(code=language_code)
#             if Localization.objects.filter(
#                     code=code,
#                     language=language
#             ).exclude(pk=self.instance.pk).exists():
#                 raise serializers.ValidationError(
#                     {"code": "Localization with this code already exists for this language."}
#                 )
#         else:  # Create case
#             language = Language.objects.get(code=language_code)
#             if Localization.objects.filter(code=code, language=language).exists():
#                 raise serializers.ValidationError(
#                     {"code": "Localization with this code already exists for this language."}
#                 )
#         return attrs
#
#     def create(self, validated_data):
#         language_code = validated_data.pop('language_code')
#         language = Language.objects.get(code=language_code)
#
#         localization = Localization.objects.create(
#             language=language,
#             **validated_data
#         )
#
#         # Set created_by
#         request = self.context.get('request')
#         if request and request.user:
#             localization.created_by = request.user
#             localization.save()
#
#         return localization
#
#     def update(self, instance, validated_data):
#         language_code = validated_data.pop('language_code', None)
#
#         if language_code:
#             language = Language.objects.get(code=language_code)
#             instance.language = language
#
#         instance.code = validated_data.get('code', instance.code)
#         instance.text = validated_data.get('text', instance.text)
#         instance.save()
#
#         return instance
class LocalizationCreateUpdateSerializer(serializers.ModelSerializer):
    language_code = serializers.CharField(write_only=True)
    module_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=True
    )

    class Meta:
        model = Localization
        fields = ['code', 'text', 'language_code', 'module_ids']

    def validate(self, attrs):
        language_code = attrs.get('language_code')
        code = attrs.get('code')
        module_ids = attrs.get('module_ids', [])

        try:
            language = Language.objects.get(code=language_code)
        except Language.DoesNotExist:
            raise serializers.ValidationError({"language_code": "Invalid language code."})

        if self.instance:  # UPDATE CASE
            # Adjusted: Allow 0 (which becomes NULL) or 1 module ID only
            if len(module_ids) > 1:
                raise serializers.ValidationError(
                    {"module_ids": "You can only select one module (or none) when editing."}
                )

            # Determine the target module ID (None if empty list)
            target_module = module_ids[0] if module_ids else None

            # Check for conflict excluding current instance
            if Localization.objects.filter(
                    code=code,
                    language=language,
                    module_id=target_module
            ).exclude(pk=self.instance.pk).exists():
                module_display = target_module if target_module else "NULL"
                raise serializers.ValidationError(
                    {"code": f"A localization for module {module_display} already exists."}
                )

        else:  # CREATE CASE
            # Handle the case where no modules are selected (module_id will be NULL)
            if not module_ids:
                if Localization.objects.filter(
                        code=code,
                        language=language,
                        module_id=None
                ).exists():
                    raise serializers.ValidationError(
                        {"module_ids": "Localization with no module (NULL) already exists."}
                    )
            else:
                # Check each module ID for existing duplicates
                for m_id in module_ids:
                    if Localization.objects.filter(
                            code=code,
                            language=language,
                            module_id=m_id
                    ).exists():
                        raise serializers.ValidationError(
                            {"module_ids": f"Localization for module ID {m_id} already exists."}
                        )

        attrs['language_obj'] = language
        return attrs

    def create(self, validated_data):
        language = validated_data.pop('language_obj')
        module_ids = validated_data.pop('module_ids')
        request = self.context.get('request')

        if not module_ids:
            return Localization.objects.create(
                language=language,
                code=validated_data.get('code'),
                text=validated_data.get('text'),
                module_id=None,
                created_by=request.user if request else None
            )
        last_instance = None
        for m_id in module_ids:
            last_instance = Localization.objects.create(
                language=language,
                code=validated_data.get('code'),
                text=validated_data.get('text'),
                module_id=m_id,
                created_by=request.user if request else None
            )
        return last_instance

    def update(self, instance, validated_data):
        language = validated_data.pop('language_obj', None)
        module_ids = validated_data.pop('module_ids', [])

        if language:
            instance.language = language

        instance.code = validated_data.get('code', instance.code)
        instance.text = validated_data.get('text', instance.text)

        # Handle the Module assignment
        if not module_ids:
            # User cleared the selection, set to NULL in DB
            instance.module_id = None
        else:
            # User selected exactly one (enforced by validate)
            instance.module_id = module_ids[0]

        instance.save()
        return instance

# ================ CUSTOM USER SERIALIZERS ================

class CustomUserSerializer(serializers.ModelSerializer):
    # Auth user fields
    username = serializers.CharField(source='auth_user.username', read_only=True)
    first_name = serializers.CharField(source='auth_user.first_name', read_only=True)
    last_name = serializers.CharField(source='auth_user.last_name', read_only=True)
    email = serializers.EmailField(source='auth_user.email', read_only=True)
    last_login = serializers.DateTimeField(source='auth_user.last_login', read_only=True)

    # Related fields
    client_username = serializers.CharField(source='client.auth_user.username', read_only=True)
    client_company = serializers.CharField(source='client.company_name', read_only=True)
    language_name = serializers.CharField(source='language.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    # Custom fields
    full_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()  # UPDATED: Use SerializerMethodField for Base64

    class Meta:
        model = CustomUser
        fields = [
            'id',
            'auth_user',
            'username',
            'first_name',
            'last_name',
            'email',
            'full_name',
            'phone',
            'avatar',
            'client',
            'client_username',
            'client_company',
            'language',
            'language_name',
            'is_active',
            'last_login',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'auth_user', 'client']

    def get_full_name(self, obj):
        return f"{obj.auth_user.first_name} {obj.auth_user.last_name}".strip() or obj.auth_user.username

    def get_avatar(self, obj):
        """Return Base64 data URI for avatar"""
        return obj.avatar  # Calls the @property method in the model


# ================ CLIENT SERIALIZERS ================

class ClientCreateUpdateSerializer(serializers.ModelSerializer):
    # Auth user fields (writable)
    username = serializers.CharField(write_only=True, required=False)
    first_name = serializers.CharField(required=False, write_only=True)
    last_name = serializers.CharField(required=False, write_only=True)
    email = serializers.EmailField(required=False, write_only=True)
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})
    is_active = serializers.BooleanField(default=True, write_only=True, required=False)

    # UPDATED: Avatar as file upload (will be converted to Base64)
    avatar = serializers.ImageField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Client
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'password',
            'phone',
            'avatar',
            'company_name',
            'language',
            'is_active'
        ]

    def validate_username(self, value):
        if self.instance:
            if User.objects.filter(username=value).exclude(pk=self.instance.auth_user.pk).exists():
                raise serializers.ValidationError("User with this username already exists.")
        else:
            if User.objects.filter(username=value).exists():
                raise serializers.ValidationError("User with this username already exists.")
        return value

    def validate_email(self, value):
        if self.instance:
            if User.objects.filter(email=value).exclude(pk=self.instance.auth_user.pk).exists():
                raise serializers.ValidationError("User with this email already exists.")
        else:
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError("User with this email already exists.")
        return value

    def validate(self, attrs):
        if not self.instance and not attrs.get('password'):
            raise serializers.ValidationError({"password": "This field is required when creating a new client."})
        return attrs

    def create(self, validated_data):
        username = validated_data.pop('username')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        is_active = validated_data.pop('is_active', True)
        avatar_file = validated_data.pop('avatar', None)  # Extract avatar file

        with transaction.atomic():
            auth_user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active
            )

            client = Client.objects.create(
                auth_user=auth_user,
                **validated_data
            )

            # UPDATED: Handle avatar upload - convert to Base64
            if avatar_file:
                file_content = avatar_file.read()
                client.avatar_base64 = base64.b64encode(file_content).decode('utf-8')
                client.avatar_filename = avatar_file.name
                client.avatar_content_type = avatar_file.content_type
                client.save()

        return client

    def update(self, instance, validated_data):
        username = validated_data.pop('username', None)
        first_name = validated_data.pop('first_name', None)
        last_name = validated_data.pop('last_name', None)
        email = validated_data.pop('email', None)
        password = validated_data.pop('password', None)
        is_active = validated_data.pop('is_active', None)
        avatar_file = validated_data.pop('avatar', None)  # Extract avatar file

        with transaction.atomic():
            auth_user = instance.auth_user
            if username:
                auth_user.username = username
            if first_name is not None:  # Allow empty string
                auth_user.first_name = first_name
            if last_name is not None:  # Allow empty string
                auth_user.last_name = last_name
            if email:
                auth_user.email = email
            if password:
                auth_user.set_password(password)
            if is_active is not None:
                auth_user.is_active = is_active
            auth_user.save()

            # Update client fields
            for key, value in validated_data.items():
                setattr(instance, key, value)

            # UPDATED: Handle avatar upload - convert to Base64
            if avatar_file:
                file_content = avatar_file.read()
                instance.avatar_base64 = base64.b64encode(file_content).decode('utf-8')
                instance.avatar_filename = avatar_file.name
                instance.avatar_content_type = avatar_file.content_type

            instance.save()

        return instance


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating admin/superuser profiles
    Note: Admins don't have avatar support unless you add it to User model
    """
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_active',
        ]
        read_only_fields = ['id', 'username']

    def update(self, instance, validated_data):
        # Update text fields
        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()
        return instance


# ================ SIMPLE STATUS UPDATE SERIALIZER ================

class SimpleStatusUpdateSerializer(serializers.Serializer):
    """Simple serializer for updating status"""
    is_active = serializers.BooleanField(required=True)


class CustomUserCreateUpdateSerializer(serializers.ModelSerializer):
    # Auth user fields (writable)
    username = serializers.CharField(write_only=True, required=False)
    first_name = serializers.CharField(required=False, write_only=True)
    last_name = serializers.CharField(required=False, write_only=True)
    email = serializers.EmailField(required=False, write_only=True)
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})
    is_active = serializers.BooleanField(default=True, write_only=True, required=False)
    client_id = serializers.IntegerField(write_only=True, required=False)

    # UPDATED: Avatar as file upload (will be converted to Base64)
    avatar = serializers.ImageField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'password',
            'phone',
            'avatar',
            'client_id',
            'language',
            'is_active'
        ]

    def validate_username(self, value):
        if self.instance:
            if User.objects.filter(username=value).exclude(pk=self.instance.auth_user.pk).exists():
                raise serializers.ValidationError("User with this username already exists.")
        else:
            if User.objects.filter(username=value).exists():
                raise serializers.ValidationError("User with this username already exists.")
        return value

    def validate_email(self, value):
        if self.instance:
            if User.objects.filter(email=value).exclude(pk=self.instance.auth_user.pk).exists():
                raise serializers.ValidationError("User with this email already exists.")
        else:
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError("User with this email already exists.")
        return value

    def validate_client_id(self, value):
        try:
            client = Client.objects.get(pk=value)
            if not client.is_active:
                raise serializers.ValidationError("Client is not active.")
        except Client.DoesNotExist:
            raise serializers.ValidationError("Client does not exist.")
        return value

    def validate(self, attrs):
        if not self.instance and not attrs.get('password'):
            raise serializers.ValidationError({"password": "This field is required when creating a new user."})
        return attrs

    def create(self, validated_data):
        username = validated_data.pop('username')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        is_active = validated_data.pop('is_active', True)
        client_id = validated_data.pop('client_id')
        avatar_file = validated_data.pop('avatar', None)  # Extract avatar file

        with transaction.atomic():
            client = Client.objects.get(pk=client_id)
            auth_user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active
            )

            custom_user = CustomUser.objects.create(
                auth_user=auth_user,
                client=client,
                **validated_data
            )

            # UPDATED: Handle avatar upload - convert to Base64
            if avatar_file:
                file_content = avatar_file.read()
                custom_user.avatar_base64 = base64.b64encode(file_content).decode('utf-8')
                custom_user.avatar_filename = avatar_file.name
                custom_user.avatar_content_type = avatar_file.content_type
                custom_user.save()

        return custom_user

    def update(self, instance, validated_data):
        username = validated_data.pop('username', None)
        first_name = validated_data.pop('first_name', None)
        last_name = validated_data.pop('last_name', None)
        email = validated_data.pop('email', None)
        password = validated_data.pop('password', None)
        is_active = validated_data.pop('is_active', None)
        client_id = validated_data.pop('client_id', None)
        avatar_file = validated_data.pop('avatar', None)  # Extract avatar file

        with transaction.atomic():
            auth_user = instance.auth_user
            if username:
                auth_user.username = username
            if first_name is not None:  # Allow empty string
                auth_user.first_name = first_name
            if last_name is not None:  # Allow empty string
                auth_user.last_name = last_name
            if email:
                auth_user.email = email
            if password:
                auth_user.set_password(password)
            if is_active is not None:
                auth_user.is_active = is_active
            auth_user.save()

            if client_id:
                instance.client = Client.objects.get(pk=client_id)

            # Update custom user fields
            for key, value in validated_data.items():
                setattr(instance, key, value)

            # UPDATED: Handle avatar upload - convert to Base64
            if avatar_file:
                file_content = avatar_file.read()
                instance.avatar_base64 = base64.b64encode(file_content).decode('utf-8')
                instance.avatar_filename = avatar_file.name
                instance.avatar_content_type = avatar_file.content_type

            instance.save()

        return instance


# ================ CLIENT SERIALIZER (READ) ================

class ClientSerializer(serializers.ModelSerializer):
    # Auth user fields
    username = serializers.CharField(source='auth_user.username', read_only=True)
    first_name = serializers.CharField(source='auth_user.first_name', read_only=True)
    last_name = serializers.CharField(source='auth_user.last_name', read_only=True)
    email = serializers.EmailField(source='auth_user.email', read_only=True)
    last_login = serializers.DateTimeField(source='auth_user.last_login', read_only=True)
    user_is_active = serializers.BooleanField(source='auth_user.is_active', read_only=True)
    payment_status = serializers.SerializerMethodField()
    # Related fields
    language_name = serializers.CharField(source='language.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    # Subscription fields
    subscription_status = serializers.SerializerMethodField()
    subscription_plan_name = serializers.SerializerMethodField()
    current_subscription = serializers.SerializerMethodField()
    current_api_calls = serializers.SerializerMethodField()
    current_minutes = serializers.SerializerMethodField()
    current_ai_tokens = serializers.SerializerMethodField()
    current_users = serializers.SerializerMethodField()
    current_ai_agents = serializers.SerializerMethodField()
    minutes_limit = serializers.SerializerMethodField()
    ai_tokens_limit = serializers.SerializerMethodField()
    user_limit = serializers.SerializerMethodField()
    agents_limit = serializers.SerializerMethodField()
    grace_ends_at = serializers.SerializerMethodField()
    ai_features_enabled = serializers.SerializerMethodField()
    next_billing_date = serializers.SerializerMethodField()
    plan_tier = serializers.SerializerMethodField()
    plan_price = serializers.SerializerMethodField()
    plan_period = serializers.SerializerMethodField()

    # Custom fields
    full_name = serializers.SerializerMethodField()
    total_users = serializers.SerializerMethodField()
    total_active_users = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()  # UPDATED: Use SerializerMethodField for Base64

    class Meta:
        model = Client
        fields = [
            'id',
            'auth_user',
            'username',
            'first_name',
            'payment_status',
            'last_name',
            'email',
            'full_name',
            'phone',
            'avatar',
            'company_name',
            'language',
            'language_name',
            'is_active',
            'user_is_active',
            'last_login',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
            'total_users',
            'total_active_users',
            # Subscription fields
            'subscription_status',
            'subscription_plan_name',
            'plan_tier',
            'plan_price',
            'plan_period',
            'current_subscription',
            'current_api_calls',
            'current_minutes',
            'current_ai_tokens',
            'current_users',
            'current_ai_agents',
            'minutes_limit',
            'ai_tokens_limit',
            'user_limit',
            'agents_limit',
            'grace_ends_at',
            'ai_features_enabled',
            'next_billing_date'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'auth_user']

    def get_full_name(self, obj):
        return f"{obj.auth_user.first_name} {obj.auth_user.last_name}".strip() or obj.auth_user.username

    def get_avatar(self, obj):
        """Return Base64 data URI for avatar"""
        return obj.avatar  # Calls the @property method in the model

        return "N/A"
    def get_total_users(self, obj):
        return obj.users.count()

    def get_payment_status(self, obj):
        """Get the payment status from the client's current subscription"""
        try:
            # We look directly at obj.subscriptions because obj IS the client
            subscription = obj.subscriptions.filter(
                status__in=['Active', 'Trial', 'Pending']
            ).order_by('-created_at').first()

            if subscription:
                return subscription.payment_status
        except Exception:
            return "N/A"

        return "N/A"
    def get_total_active_users(self, obj):
        return obj.users.filter(is_active=True).count()

    # ================ SUBSCRIPTION METHODS ================

    def get_subscription_status(self, obj):
        """Get current subscription status"""
        try:
            if hasattr(obj, 'subscriptions'):
                subscription = obj.subscriptions.filter(status__in=['Active', 'Trial']).order_by('-created_at').first()
                if subscription:
                    return subscription.status.lower()
            return "no_subscription"
        except Exception:
            return "no_subscription"

    def get_subscription_plan_name(self, obj):
        """Get current subscription plan name"""
        try:
            if hasattr(obj, 'subscriptions'):
                subscription = obj.subscriptions.filter(status__in=['Active', 'Trial']).order_by('-created_at').first()
                if subscription and hasattr(subscription, 'plan') and subscription.plan:
                    return subscription.plan.name
            return "No Plan"
        except Exception:
            return "No Plan"

    def get_plan_tier(self, obj):
        """Get current plan tier"""
        try:
            if hasattr(obj, 'subscriptions'):
                subscription = obj.subscriptions.filter(status__in=['Active', 'Trial']).order_by('-created_at').first()
                if subscription and hasattr(subscription, 'plan') and subscription.plan:
                    return subscription.plan.tier
            return None
        except Exception:
            return None

    def get_plan_price(self, obj):
        """Get current plan price"""
        try:
            if hasattr(obj, 'subscriptions'):
                subscription = obj.subscriptions.filter(status__in=['Active', 'Trial']).order_by('-created_at').first()
                if subscription and hasattr(subscription, 'plan') and subscription.plan:
                    return str(subscription.plan.price) if subscription.plan.price else "0"
            return "0"
        except Exception:
            return "0"

    def get_plan_period(self, obj):
        """Get current plan period"""
        try:
            if hasattr(obj, 'subscriptions'):
                subscription = obj.subscriptions.filter(status__in=['Active', 'Trial']).order_by('-created_at').first()
                if subscription and hasattr(subscription, 'plan') and subscription.plan:
                    return subscription.plan.period
            return None
        except Exception:
            return None

    def get_current_subscription(self, obj):
        """Get current subscription ID"""
        try:
            if hasattr(obj, 'subscriptions'):
                subscription = obj.subscriptions.filter(status__in=['Active', 'Trial']).order_by('-created_at').first()
                if subscription:
                    return subscription.id
            return None
        except Exception:
            return None

    def get_current_api_calls(self, obj):
        """Get current API calls usage (not tracked yet)."""
        return 0

    def _get_usage_snapshot(self, obj):
        from EduraAPI.apps.subscription.services.usage import build_usage_snapshot
        return build_usage_snapshot(obj)

    def get_current_minutes(self, obj):
        try:
            return self._get_usage_snapshot(obj).get("minutes_used", 0)
        except Exception:
            return 0

    def get_current_ai_tokens(self, obj):
        try:
            return self._get_usage_snapshot(obj).get("ai_tokens_used", 0)
        except Exception:
            return 0

    def get_current_users(self, obj):
        try:
            return self._get_usage_snapshot(obj).get("users_count", 0)
        except Exception:
            return 0

    def get_current_ai_agents(self, obj):
        try:
            return self._get_usage_snapshot(obj).get("agents_count", 0)
        except Exception:
            return 0

    def get_minutes_limit(self, obj):
        try:
            return self._get_usage_snapshot(obj).get("minutes_limit", 0)
        except Exception:
            return 0

    def get_ai_tokens_limit(self, obj):
        try:
            return self._get_usage_snapshot(obj).get("ai_tokens_limit", 0)
        except Exception:
            return 0

    def get_user_limit(self, obj):
        try:
            return self._get_usage_snapshot(obj).get("user_limit", 0)
        except Exception:
            return 0

    def get_agents_limit(self, obj):
        try:
            return self._get_usage_snapshot(obj).get("agents_limit", 0)
        except Exception:
            return 0

    def get_grace_ends_at(self, obj):
        try:
            from EduraAPI.apps.subscription.services.access import get_client_subscription
            subscription = get_client_subscription(obj)
            if subscription and subscription.emergency_grace_ends_at:
                return subscription.emergency_grace_ends_at.isoformat()
            return None
        except Exception:
            return None

    def get_ai_features_enabled(self, obj):
        try:
            from EduraAPI.apps.subscription.services.usage import build_access_status
            return build_access_status(obj).get("ai_enabled", False)
        except Exception:
            return False

    def get_next_billing_date(self, obj):
        """Get next billing date"""
        try:
            if hasattr(obj, 'subscriptions'):
                subscription = obj.subscriptions.filter(status__in=['Active', 'Trial']).order_by('-created_at').first()
                if subscription:
                    return subscription.next_billing_date
            return None
        except Exception:
            return None
