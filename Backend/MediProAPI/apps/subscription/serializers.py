from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import SubscriptionPlan, ClientSubscription, SubscriptionInvoice, SubscriptionType, SubscriptionPlanModule
from .services.plan_modules import sync_plan_modules, get_plan_module_ids
from decimal import Decimal,InvalidOperation

User = get_user_model()


# ================ SUBSCRIPTION PLAN SERIALIZERS ================
class SubscriptionTypeSerializer(serializers.ModelSerializer):
    """Serializer for subscription types (Monthly / Yearly)"""

    class Meta:
        model = SubscriptionType
        fields = ['id', 'name']
class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for reading subscription plans"""
    display_price = serializers.SerializerMethodField()
    yearly_price = serializers.SerializerMethodField()
    monthly_price = serializers.SerializerMethodField()
    features_list = serializers.SerializerMethodField()
    usage_limits = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    discounted_price = serializers.DecimalField(
        source='get_monthly_price',  # Uses the method we created in the model
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    yearly_discounted_price = serializers.DecimalField(
        source='get_yearly_price',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    tax_amount = serializers.DecimalField(
        source='get_tax_amount',  # Calls the method in your model
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    total_price = serializers.DecimalField(
        source='get_total_price_with_tax',  # Calls the method in your model
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    monthly_total_price = serializers.SerializerMethodField()
    yearly_total_price = serializers.SerializerMethodField()
    default_module_ids = serializers.SerializerMethodField()
    default_modules = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id',
            'name',
            'tier',
            'description',
            'price',
            'display_price',
            'yearly_price',
            'monthly_price',
            'discounted_price',
            'yearly_discounted_price',
            'discount_percentage',
            # Usage limits
            'user_limit',
            'api_calls_per_month',
            'minutes_per_month',
            'ai_tokens_per_month',
            'embeddings_per_month',
            'ai_agents_count',

            # Features list for display
            'features_list',
            'usage_limits',

            # Tax
            'tax_rate',
            'tax_amount',
            'total_price',
            'monthly_total_price',
            'yearly_total_price',
            'default_module_ids',
            'default_modules',
            # Metadata
            'is_active',
            'is_popular',
            'sort_order',
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def get_display_price(self, obj):
        return obj.get_display_price()

    def get_yearly_price(self, obj):
        return obj.get_yearly_price()

    def get_monthly_price(self, obj):
        return obj.get_monthly_price()

    def get_features_list(self, obj):
        return obj.get_features_list()

    def get_monthly_total_price(self, obj):
        return obj.get_total_price_with_tax()

    def get_yearly_total_price(self, obj):
        yearly_price = obj.get_yearly_price()
        tax = (yearly_price * obj.tax_rate) / Decimal('100')
        return yearly_price + tax

    def get_usage_limits(self, obj):
        return obj.get_usage_limits()

    def get_default_module_ids(self, obj):
        return get_plan_module_ids(obj.id)

    def get_default_modules(self, obj):
        rows = SubscriptionPlanModule.objects.filter(plan=obj).select_related('module').order_by('sequence', 'module_id')
        return [
            {
                'module_id': row.module_id,
                'code': row.module.code,
                'description': row.module.description,
                'icon': row.module.icon,
                'sequence': row.sequence,
                'parent_id': row.parent_id,
            }
            for row in rows
        ]


class SubscriptionPlanCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating subscription plans"""
    module_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )
    discount_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        required=False,
        allow_null=False  # This prevents NULL from reaching the database
    )
    tax_amount = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    class Meta:
        model = SubscriptionPlan
        fields = [
            'name',
            'tier',
            'description',
            'price',
            'discount_percentage',


            # Usage limits
            'user_limit',
            'api_calls_per_month',
            'minutes_per_month',
            'ai_tokens_per_month',
            'embeddings_per_month',
            'ai_agents_count',

            # Tax
            'tax_rate',
            'tax_amount',  # Computed
            'total_price',


            # Metadata
            'is_active',
            'is_popular',
            'sort_order',
            'module_ids',
        ]

    read_only_fields = ['discounted_price', 'tax_amount', 'total_price']
    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value

    def validate_discount_percentage(self, value):
        # DRF's DecimalField already converted 'value' to a Decimal object here
        if value is None:
            return Decimal('0.00')

        if value < 0 or value > 100:
            raise serializers.ValidationError("Discount must be between 0 and 100.")

        return value

    def get_tax_amount(self, obj):
        return obj.get_tax_amount()

    def get_total_price(self, obj):
        return obj.get_total_price_with_tax()

    def validate_user_limit(self, value):
        if value < 1:
            raise serializers.ValidationError("User limit must be at least 1.")
        return value

    def validate_tax_rate(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Tax rate must be between 0 and 100.")
        return value

    def create(self, validated_data):
        module_ids = validated_data.pop('module_ids', None)
        request = self.context.get('request')
        if request and request.user:
            validated_data['created_by'] = request.user
        plan = super().create(validated_data)
        if module_ids is not None:
            try:
                sync_plan_modules(plan, module_ids)
            except ValueError as exc:
                raise serializers.ValidationError({'module_ids': str(exc)}) from exc
        return plan

    def update(self, instance, validated_data):
        module_ids = validated_data.pop('module_ids', None)
        plan = super().update(instance, validated_data)
        if module_ids is not None:
            try:
                sync_plan_modules(plan, module_ids)
            except ValueError as exc:
                raise serializers.ValidationError({'module_ids': str(exc)}) from exc
        return plan


class PaymentUpdateSerializer(serializers.Serializer):
    # Matches item.id from your Vue component
    user_id = serializers.IntegerField(required=True)

    # allow_null=True handles users without a plan
    plan_id = serializers.IntegerField(required=False, allow_null=True)

    # Sync these with your PAYMENT_STATUS_CHOICES
    payment_status = serializers.ChoiceField(
        choices=[
            ('Pending', 'Pending'),
            ('Paid', 'Paid'),
            ('Failed', 'Failed'),
            ('Refunded', 'Refunded'),
            ('Processing', 'Processing'),
        ]
    )

    def validate_user_id(self, value):
        """Optional: Ensure the user actually exists"""
        # from django.contrib.auth.models import User
        # if not User.objects.filter(id=value).exists():
        #     raise serializers.ValidationError("User not found.")
        return value
# ================ CLIENT SUBSCRIPTION SERIALIZERS ================

class ClientSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for reading client subscriptions"""
    client_details = serializers.SerializerMethodField()
    plan_details = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    has_invoice = serializers.SerializerMethodField()
    latest_invoice = serializers.SerializerMethodField()
    subscription_type_id = serializers.IntegerField(
        source='subscription_type.id',
        read_only=True
    )

    class Meta:
        model = ClientSubscription
        fields = [
            'id',
            'client',
            'client_details',
            'payment_status',
            'plan',
            'plan_details',
            'subscription_type_id',

            # Subscription details
            'billing_cycle',
            'status',
            'payment_status',
            'is_active',
            'days_remaining',

            # Dates
            'start_date',
            'end_date',
            'trial_end_date',
            'cancelled_at',
            'next_billing_date',

            # Payment info
            'amount',
            'currency',

            # Invoice info
            'has_invoice',
            'latest_invoice',

            # Metadata
            'auto_renew',
            'cancellation_reason',

            # Timestamps
            'created_at',
            'updated_at',
            'created_by',
            'created_by_name',
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def get_client_details(self, obj):
        return {
            'id': obj.client.id,
            'company_name': obj.client.company_name,
            'email': obj.client.auth_user.email,
            'username': obj.client.auth_user.username,
        }

    def get_plan_details(self, obj):
        return {
            'id': obj.plan.id,
            'name': obj.plan.name,
            'tier': obj.plan.tier,
            'price': obj.plan.price,
            'user_limit': obj.plan.user_limit,
            'ai_agents_count': obj.plan.ai_agents_count,
        }

    def get_is_active(self, obj):
        return obj.is_active()

    def get_days_remaining(self, obj):
        return obj.days_remaining()

    def get_has_invoice(self, obj):
        return obj.invoices.exists()

    def get_latest_invoice(self, obj):
        latest = obj.invoices.first()
        if latest:
            return {
                'id': latest.id,
                'invoice_number': latest.invoice_number,
                'status': latest.status,
                'total_amount': str(latest.total_amount),
                'due_date': latest.due_date,
                'is_overdue': latest.is_overdue()
            }
        return None


class ClientSubscriptionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating client subscriptions"""
    client_id = serializers.IntegerField(write_only=True)
    plan_id = serializers.IntegerField(write_only=True)
    billing_cycle = serializers.ChoiceField(choices=ClientSubscription.BILLING_CYCLE_CHOICES, default='Monthly')
    start_date = serializers.DateField(required=False)
    subscription_type_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ClientSubscription
        fields = [
            'client_id',
            'plan_id',
            'billing_cycle',
            'subscription_type_id',
            'payment_status',
            'start_date',
            'auto_renew',
        ]

    def validate_subscription_type_id(self, value):
        try:
            sub_type = SubscriptionType.objects.get(id=value)
            return sub_type.id  # <-- return ID, not the object
        except SubscriptionType.DoesNotExist:
            raise serializers.ValidationError("Invalid subscription type.")

    def validate_client_id(self, value):
        from MediProAPI.apps.users.models import Client
        try:
            client = Client.objects.get(id=value, is_active=True)
        except Client.DoesNotExist:
            raise serializers.ValidationError("Client not found or inactive.")
        return value

    def validate_plan_id(self, value):
        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Subscription plan not found or inactive.")
        return value

    def validate(self, attrs):
        from MediProAPI.apps.users.models import Client

        client_id = attrs.get('client_id')
        plan_id = attrs.get('plan_id')

        # Check if client already has an active subscription
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            raise serializers.ValidationError({
                'client_id': 'Client not found.'
            })

        active_subscriptions = client.subscriptions.filter(
            status__in=['Active', 'Trial']
        )

        if active_subscriptions.exists():
            raise serializers.ValidationError({
                'client_id': 'Client already has an active subscription.'
            })

        return attrs

    def create(self, validated_data):
        from MediProAPI.apps.users.models import Client
        from datetime import timedelta

        # Pop write-only fields
        client_id = validated_data.pop('client_id')
        plan_id = validated_data.pop('plan_id')
        subscription_type_id = validated_data.pop('subscription_type_id')
        subscription_type = SubscriptionType.objects.get(id=subscription_type_id)

        # Get the actual objects
        client = Client.objects.get(id=client_id)
        plan = SubscriptionPlan.objects.get(id=plan_id)


        # Set start date
        start_date = validated_data.pop('start_date', timezone.now().date())

        # Create subscription
        subscription = ClientSubscription(
            client=client,
            plan=plan,
            subscription_type=subscription_type,  # ✅ model instance
            start_date=start_date,
            **validated_data
        )

        # Amount calculation based on subscription type
        if subscription_type.id == 1:  # Monthly
            subscription.amount = plan.get_monthly_price()
        elif subscription_type.id == 2:  # Yearly
            subscription.amount = plan.get_monthly_price() * 12
        else:
            subscription.amount = plan.get_monthly_price()  # fallback

        # Assign created_by
        request = self.context.get('request')
        if request and request.user:
            subscription.created_by = request.user

        subscription.save()

        return subscription


class ClientSubscriptionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating client subscriptions"""

    class Meta:
        model = ClientSubscription
        fields = [
            'auto_renew',
            'notes',
            'payment_method',
        ]

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance


class SubscriptionActivateSerializer(serializers.Serializer):
    """Serializer for activating subscription"""
    payment_method = serializers.CharField(required=False)
    stripe_payment_intent_id = serializers.CharField(required=False)

    def validate(self, attrs):
        if not attrs.get('payment_method') and not attrs.get('stripe_payment_intent_id'):
            raise serializers.ValidationError(
                "Either payment_method or stripe_payment_intent_id is required."
            )
        return attrs


class SubscriptionEndSerializer(serializers.Serializer):
    """Serializer for ending subscription"""
    reason = serializers.CharField(required=True)
    immediate = serializers.BooleanField(default=False)

    def validate_reason(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError(
                "Please provide a detailed reason (minimum 10 characters)."
            )
        return value


# ================ INVOICE SERIALIZERS ================

class SubscriptionInvoiceSerializer(serializers.ModelSerializer):
    """Serializer for subscription invoices"""
    subscription_details = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()
    invoice_items = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()
    client_details = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionInvoice
        fields = [
            'id',
            'subscription',
            'subscription_details',
            'client_details',
            'invoice_number',
            'status',

            # Amount details
            'amount',
            'tax_amount',
            'discount_amount',
            'total_amount',
            'currency',

            # Dates
            'issue_date',
            'due_date',
            'paid_date',
            'is_overdue',
            'days_overdue',

            # Payment info
            'stripe_invoice_id',
            'stripe_payment_intent_id',

            # PDF info
            'pdf_file',
            'pdf_url',
            'pdf_generated_at',

            # Alert tracking
            'overdue_alert_sent',
            'overdue_alert_sent_at',
            'reminder_sent',
            'reminder_sent_at',

            # Metadata
            'description',
            'notes',
            'invoice_items',

            # Timestamps
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'pdf_generated_at']

    def get_subscription_details(self, obj):
        return {
            'id': obj.subscription.id,
            'client_company': obj.subscription.client.company_name,
            'plan_name': obj.subscription.plan.name,
            'billing_cycle': obj.subscription.billing_cycle,
        }

    def get_client_details(self, obj):
        return {
            'id': obj.subscription.client.id,
            'company_name': obj.subscription.client.company_name,
            'email': obj.subscription.client.auth_user.email,
        }

    def get_is_overdue(self, obj):
        return obj.is_overdue()

    def get_days_overdue(self, obj):
        return obj.days_overdue()

    def get_invoice_items(self, obj):
        return obj.get_invoice_items()

    def get_pdf_url(self, obj):
        if obj.pdf_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.pdf_file.url)
            return obj.pdf_file.url
        return None


# ================ CLIENT WITH SUBSCRIPTION SERIALIZERS ================

class ClientWithSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for clients with their subscription info"""
    current_subscription = serializers.SerializerMethodField()
    subscription_history = serializers.SerializerMethodField()

    class Meta:
        from MediProAPI.apps.users.models import Client
        model = Client
        fields = [
            'id',
            'company_name',
            'auth_user',
            'is_active',
            'created_at',
            'updated_at',
            'current_subscription',
            'subscription_history',
        ]

    def get_current_subscription(self, obj):
        active_subscription = obj.subscriptions.filter(
            status__in=['Active', 'Trial']
        ).first()

        if active_subscription:
            return ClientSubscriptionSerializer(active_subscription).data
        return None

    def get_subscription_history(self, obj):
        subscriptions = obj.subscriptions.exclude(
            status__in=['Active', 'Trial']
        ).order_by('-created_at')[:10]

        return ClientSubscriptionSerializer(subscriptions, many=True).data