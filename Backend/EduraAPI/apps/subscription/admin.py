from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import SubscriptionPlan, ClientSubscription, SubscriptionInvoice


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'tier', 'price',  'user_limit', 'ai_agents_count', 'is_active', 'is_popular')
    list_filter = ('tier', 'is_active', 'is_popular')
    search_fields = ('name', 'description', 'tier')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'tier', 'description', 'price', 'tax_rate')
        }),
        ('Usage Limits', {
            'fields': ('user_limit', 'api_calls_per_month', 'minutes_per_month',
                       'ai_tokens_per_month', 'ai_agents_count')
        }),
        ('Metadata', {
            'fields': ('is_active', 'is_popular', 'sort_order', 'created_by', 'created_at', 'updated_at')
        }),
    )


@admin.register(ClientSubscription)
class ClientSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'plan', 'status', 'billing_cycle', 'start_date', 'end_date', 'amount',
                    'has_invoice')

    list_filter = ('status', 'payment_status', 'billing_cycle', 'plan__tier')

    search_fields = ('client__company_name', 'client__auth_user__email', 'plan__name')
    readonly_fields = ('id', 'created_at', 'updated_at')

    fieldsets = (
        ('Subscription Details', {
            'fields': ('id', 'client', 'plan', 'billing_cycle', 'status', 'payment_status')
        }),
        ('Dates', {

            'fields': ('start_date', 'end_date', 'cancelled_at', 'next_billing_date')
        }),
        ('Payment Info', {

            'fields': ('amount', 'currency')
        }),

        ('Metadata', {

            'fields': ('auto_renew', 'cancellation_reason', 'created_by', 'created_at', 'updated_at')
        }),
    )

    def has_invoice(self, obj):
        return obj.invoices.exists()

    has_invoice.boolean = True
    has_invoice.short_description = 'Has Invoice'



@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice_number', 'subscription_info', 'status', 'total_amount',
                    'issue_date', 'due_date', 'is_overdue', 'has_pdf', 'alert_status')
    list_filter = ('status', 'currency', 'overdue_alert_sent', 'reminder_sent')
    search_fields = ('invoice_number', 'subscription__client__company_name', 'stripe_invoice_id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'pdf_generated_at', 'pdf_file_link')

    fieldsets = (
        ('Invoice Information', {
            'fields': ('id', 'subscription', 'invoice_number', 'status', 'description')
        }),
        ('Amounts', {
            'fields': ('amount', 'tax_amount', 'discount_amount', 'total_amount', 'currency')
        }),
        ('Dates', {
            'fields': ('issue_date', 'due_date', 'paid_date')
        }),
        ('Payment Integration', {
            'fields': ('stripe_invoice_id', 'stripe_payment_intent_id')
        }),
        ('PDF Document', {
            'fields': ('pdf_file', 'pdf_file_link', 'pdf_generated_at')
        }),
        ('Alert Tracking', {
            'fields': ('overdue_alert_sent', 'overdue_alert_sent_at',
                       'reminder_sent', 'reminder_sent_at')
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_at', 'updated_at')
        }),
    )

    actions = ['generate_pdfs', 'send_overdue_alerts', 'mark_as_paid']

    def subscription_info(self, obj):
        return f"{obj.subscription.client.company_name} - {obj.subscription.plan.name}"

    subscription_info.short_description = 'Subscription'

    def is_overdue(self, obj):
        return obj.is_overdue()

    is_overdue.boolean = True
    is_overdue.short_description = 'Overdue'

    def has_pdf(self, obj):
        return bool(obj.pdf_file)

    has_pdf.boolean = True
    has_pdf.short_description = 'PDF Available'

    def pdf_file_link(self, obj):
        if obj.pdf_file:
            return format_html(
                '<a href="{}" target="_blank">Download PDF</a>',
                obj.pdf_file.url
            )
        return "No PDF available"

    pdf_file_link.short_description = 'PDF Download'

    def alert_status(self, obj):
        alerts = []
        if obj.overdue_alert_sent:
            alerts.append('Overdue Alert Sent')
        if obj.reminder_sent:
            alerts.append('Reminder Sent')
        return ', '.join(alerts) if alerts else 'No alerts sent'

    alert_status.short_description = 'Alerts'

    def generate_pdfs(self, request, queryset):
        from .utils import generate_invoice_pdf

        success_count = 0
        error_count = 0

        for invoice in queryset:
            try:
                generate_invoice_pdf(invoice.id)
                success_count += 1
            except Exception as e:
                error_count += 1

        self.message_user(
            request,
            f"Generated {success_count} PDFs successfully. {error_count} errors."
        )

    generate_pdfs.short_description = "Generate PDFs for selected invoices"

    def send_overdue_alerts(self, request, queryset):
        from .utils import send_overdue_alert

        success_count = 0
        error_count = 0

        overdue_invoices = queryset.filter(status='Overdue', overdue_alert_sent=False)

        for invoice in overdue_invoices:
            try:
                if send_overdue_alert(invoice):
                    success_count += 1
                else:
                    error_count += 1
            except Exception:
                error_count += 1

        self.message_user(
            request,
            f"Sent {success_count} alerts successfully. {error_count} errors."
        )

    send_overdue_alerts.short_description = "Send overdue alerts for selected invoices"

    def mark_as_paid(self, request, queryset):
        from django.utils import timezone

        updated = queryset.update(
            status='Paid',
            paid_date=timezone.now().date()
        )

        self.message_user(
            request,
            f"Marked {updated} invoices as paid."
        )

    mark_as_paid.short_description = "Mark selected invoices as paid"