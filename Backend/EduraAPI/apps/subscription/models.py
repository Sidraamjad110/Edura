from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import random
from datetime import timedelta
import string

User = get_user_model()


class SubscriptionType(models.Model):
    """
    Simple table for subscription types (Monthly/Yearly)
    Only has id and name
    """
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'subscription_types'
        verbose_name = 'Subscription Type'
        verbose_name_plural = 'Subscription Types'

    def __str__(self):
        return self.name

class SubscriptionPlan(models.Model):
    """
    Subscription plan master table
    """
    PLAN_TIERS = [
        ('Basic', 'Basic'),
        ('Pro', 'Pro'),
        ('Enterprise', 'Enterprise'),
        ('Custom', 'Custom'),
    ]

    # Changed from UUID to Integer
    id = models.AutoField(primary_key=True)

    # Basic info
    name = models.CharField(max_length=200)
    tier = models.CharField(max_length=20, choices=PLAN_TIERS, default='Basic')
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Discount percentage (0 to 100)"
    )

    # Usage limits
    user_limit = models.PositiveIntegerField(default=10, help_text="Maximum number of users")
    api_calls_per_month = models.PositiveIntegerField(default=50000, help_text="API calls per month")
    minutes_per_month = models.PositiveIntegerField(default=2000, help_text="Minutes per month")
    ai_tokens_per_month = models.PositiveIntegerField(default=1000000, help_text="AI tokens per month")
    embeddings_per_month = models.PositiveIntegerField(
        default=20000,
        help_text="Embeddings limit per month (document upload indexing)",
    )
    ai_agents_count = models.PositiveIntegerField(default=1, help_text="Number of AI Agents included")

    # Plan metadata
    is_active = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False, verbose_name="Mark as Popular Plan")
    sort_order = models.PositiveIntegerField(default=0, help_text="Order in which plans are displayed")

    # Tax settings
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Tax rate in percentage")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_plans')

    class Meta:
        db_table = 'subscription_plans'
        verbose_name = 'Subscription Plan'
        verbose_name_plural = 'Subscription Plans'
        ordering = ['sort_order', 'price']
        indexes = [
            models.Index(fields=['tier', 'is_active']),
            models.Index(fields=['price']),
        ]

    def __str__(self):
        return f"{self.name} - ${self.price}"

    def calculate_tax_amount(self, amount):
        """Calculate tax amount based on tax rate"""
        return (amount * self.tax_rate) / 100

    def get_discounted_price(self):
        """Calculates the price after applying the discount percentage"""
        if self.discount_percentage > 0:
            # Wrap 100 in Decimal to ensure precision math
            discount_amount = (self.price * self.discount_percentage) / Decimal('100')
            return self.price - discount_amount
        return self.price
    def get_monthly_price(self):
        """Return monthly price (assume 'price' is monthly)"""
        return self.get_discounted_price()

    def get_yearly_price(self):
        """Return yearly price (monthly * 12)"""
        return self.get_monthly_price() * 12

    def get_tax_amount(self):
        """Calculates the tax value based on the discounted price"""
        discounted_price = self.get_discounted_price()
        return (discounted_price * self.tax_rate) / Decimal('100')

    def get_total_price_with_tax(self):
        """The final amount the customer actually pays"""
        return self.get_discounted_price() + self.get_tax_amount()

    def get_features_list(self):
        """Get list of enabled features for display"""
        features = []
        features.append(f"Up to {self.user_limit} Users")
        return features

    def get_display_price(self):
        discounted = self.get_monthly_price()
        if self.discount_percentage > 0:
            return f"${discounted}/month (Original: ${self.price})"
        return f"${self.price}/month"
    def get_usage_limits(self):
        """Get usage limits as dictionary"""
        return {
            'user_limit': self.user_limit,
            'api_calls_per_month': self.api_calls_per_month,
            'minutes_per_month': self.minutes_per_month,
            'ai_tokens_per_month': self.ai_tokens_per_month,
            'embeddings_per_month': self.embeddings_per_month,
            'ai_agents_count': self.ai_agents_count,
        }


class SubscriptionPlanModule(models.Model):
    """
    Default modules included with a subscription plan template.
    When a plan is assigned to a client, these modules are auto-assigned
    to the client's auth user in user_modules.
    """
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.CASCADE,
        related_name='plan_modules',
        db_column='plan_id',
    )
    module = models.ForeignKey(
        'modules.Module',
        on_delete=models.CASCADE,
        related_name='subscription_plans',
        db_column='module_id',
    )
    sequence = models.PositiveIntegerField(default=0)
    parent_id = models.IntegerField(
        null=True,
        blank=True,
        default=None,
        help_text='Optional parent module_id in the client sidebar tree',
    )

    class Meta:
        db_table = 'subscription_plan_modules'
        unique_together = ['plan', 'module']
        ordering = ['sequence', 'module_id']
        verbose_name = 'Subscription Plan Module'
        verbose_name_plural = 'Subscription Plan Modules'

    def __str__(self):
        return f'{self.plan.name} → {self.module.code}'


class ClientSubscription(models.Model):
    """
    Subscription assignment to clients
    """
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Pending', 'Pending'),
        ('Expired', 'Expired'),
        ('Cancelled', 'Cancelled'),
        ('Suspended', 'Suspended'),
        ('Trial', 'Trial'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Failed', 'Failed'),
        ('Refunded', 'Refunded'),
        ('Processing', 'Processing'),
    ]

    BILLING_CYCLE_CHOICES = [
        ('Monthly', 'Monthly'),
        ('Yearly', 'Yearly'),
    ]

    # Changed from UUID to Integer
    id = models.AutoField(primary_key=True)

    # References (Only for Client, not User)
    client = models.ForeignKey(
        'users.Client',
        on_delete=models.CASCADE,
        related_name='subscriptions',
        db_column='client_id'
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='client_subscriptions',
        db_column='plan_id'
    )
    subscription_type = models.ForeignKey(
        'SubscriptionType',
        on_delete=models.SET_NULL,
        null=True,  # allow nulls temporarily for existing rows
        blank=True,
        related_name='subscriptions'
    )
    # Subscription details
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, default='Monthly')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Pending')

    # Dates
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    trial_end_date = models.DateField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True)

    # Payment info
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='USD')

    # Metadata
    auto_renew = models.BooleanField(default=True)
    cancellation_reason = models.TextField(blank=True, null=True)

    # Usage tracking (current billing period)
    minutes_used = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        help_text="Fractional minutes consumed this billing period",
    )
    ai_tokens_used = models.BigIntegerField(
        default=0,
        help_text="AI tokens consumed this billing period",
    )
    embeddings_used = models.BigIntegerField(
        default=0,
        help_text="Embeddings consumed this billing period (not refunded on document delete)",
    )
    usage_period_start = models.DateField(
        null=True,
        blank=True,
        help_text="Start of current usage billing window",
    )
    emergency_grace_ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Client-only emergency 24hr grace access expiry",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_subscriptions')

    class Meta:
        db_table = 'client_subscriptions'
        verbose_name = 'Client Subscription'
        verbose_name_plural = 'Client Subscriptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['status', 'end_date']),
            models.Index(fields=['end_date']),
        ]

    def __str__(self):
        return f"{self.client.company_name} - {self.plan.name} ({self.status})"

    def save(self, *args, **kwargs):
        # Set end date based on billing cycle
        if self.start_date:
            if not self.end_date or not self.next_billing_date:
                days = 30 if self.billing_cycle == 'Monthly' else 365

                # if end date empty then
                if not self.end_date:
                    self.end_date = self.start_date + timedelta(days=days)

                # Next billing date same as end_date
                if not self.next_billing_date:
                    self.next_billing_date = self.end_date

        # Set amount from plan price
        if not self.amount and self.plan:
            if self.billing_cycle == 'Monthly':
                self.amount = self.plan.get_monthly_price()
            elif self.billing_cycle == 'Yearly':
                self.amount = self.plan.get_yearly_price()

        super().save(*args, **kwargs)

    def is_active(self):
        """Check if subscription is currently active"""
        now = timezone.now().date()
        return self.status == 'Active' and self.start_date <= now <= self.end_date

    def is_trial_active(self):
        now = timezone.now().date()
        return self.status == 'Trial' and self.start_date <= now <= self.end_date

    def reset_usage_period(self):
        """Reset usage counters for a new billing period."""
        self.minutes_used = 0
        self.ai_tokens_used = 0
        self.embeddings_used = 0
        self.usage_period_start = self.start_date
        self.emergency_grace_ends_at = None

    def grace_is_active(self):
        if not self.emergency_grace_ends_at:
            return False
        return self.emergency_grace_ends_at > timezone.now()

    def days_remaining(self):
        """Get days remaining in subscription"""
        now = timezone.now().date()
        if self.end_date and now <= self.end_date:
            return (self.end_date - now).days
        return 0

    def calculate_next_billing_date(self):
        """Calculate next billing date"""
        if self.billing_cycle == 'Monthly':
            return self.end_date
        elif self.billing_cycle == 'Yearly':
            return self.end_date
        return None


class SubscriptionInvoice(models.Model):
    """
    Invoices for subscriptions with PDF generation support
    """
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Paid', 'Paid'),
        ('Overdue', 'Overdue'),
        ('Void', 'Void'),
    ]

    # Changed from UUID to Integer
    id = models.AutoField(primary_key=True)

    subscription = models.ForeignKey(
        ClientSubscription,
        on_delete=models.CASCADE,
        related_name='invoices',
        db_column='subscription_id'
    )
    invoice_number = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    # Amount details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')

    # Dates
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)

    # Payment info
    stripe_invoice_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)

    # PDF Storage
    pdf_file = models.FileField(upload_to='invoices/pdfs/', blank=True, null=True)
    pdf_generated_at = models.DateTimeField(null=True, blank=True)

    # Alert tracking
    overdue_alert_sent = models.BooleanField(default=False)
    overdue_alert_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    description = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscription_invoices'
        verbose_name = 'Subscription Invoice'
        verbose_name_plural = 'Subscription Invoices'
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['subscription', 'status']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.subscription.client.company_name}"

    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.status == 'Paid':
            return False
        now = timezone.now().date()
        return now > self.due_date

    def days_overdue(self):
        """Get number of days overdue"""
        if not self.is_overdue():
            return 0
        now = timezone.now().date()
        return (now - self.due_date).days

    def get_invoice_items(self):
        """Get invoice items description"""
        items = []
        items.append({
            'description': f"{self.subscription.plan.name} Subscription ({self.subscription.billing_cycle})",
            'quantity': 1,
            'unit_price': float(self.amount),
            'total': float(self.amount)
        })

        if self.discount_amount > 0:
            items.append({
                'description': 'Discount',
                'quantity': 1,
                'unit_price': float(-self.discount_amount),
                'total': float(-self.discount_amount)
            })

        return items

    @staticmethod
    def generate_invoice_number():
        """Generate unique invoice number"""
        timestamp = timezone.now().strftime('%Y%m%d')
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"INV-{timestamp}-{random_part}"


# Signal to auto-generate invoice when subscription is created or activated
@receiver(post_save, sender=ClientSubscription)
def create_subscription_invoice(sender, instance, created, **kwargs):
    """
    Auto-generate invoice when subscription is created or activated
    """
    from datetime import timedelta

    # Only create invoice for new subscriptions or when status changes to Active/Trial
    should_create_invoice = (
            created or
            (instance.status in ['Active', 'Trial'] and
             not instance.invoices.filter(status__in=['Draft', 'Sent', 'Paid']).exists())
    )

    if should_create_invoice and instance.status in ['Active', 'Trial', 'Pending']:
        # Calculate amounts
        base_amount = instance.amount
        tax_amount = instance.plan.calculate_tax_amount(base_amount)
        total_amount = base_amount + tax_amount

        # Set due date (7 days from issue date for monthly, 14 for yearly)
        due_days = 14 if instance.billing_cycle == 'Yearly' else 7
        due_date = timezone.now().date() + timedelta(days=due_days)

        # Create invoice
        invoice = SubscriptionInvoice.objects.create(
            subscription=instance,
            invoice_number=SubscriptionInvoice.generate_invoice_number(),
            amount=base_amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            currency=instance.currency,
            due_date=due_date,
            status='Sent' if instance.status in ['Active', 'Trial'] else 'Draft',
            description=f"{instance.plan.name} Subscription - {instance.billing_cycle} billing"
        )

        # Generate PDF asynchronously (will be handled in utils.py)
        from .utils import generate_invoice_pdf
        try:
            generate_invoice_pdf(invoice.id)
        except Exception as e:
            print(f"Error generating PDF for invoice {invoice.id}: {str(e)}")