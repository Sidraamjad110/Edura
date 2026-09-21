"""
Management command to check and send subscription alerts
Run this command daily via cron job or celery beat

Usage:
python manage.py check_subscription_alerts
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from subscriptions.utils import (
    check_overdue_invoices,
    send_overdue_alert,
    check_upcoming_due_invoices,
    send_invoice_reminder
)
from subscriptions.models import ClientSubscription


class Command(BaseCommand):
    help = 'Check and send subscription and invoice alerts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reminder-days',
            type=int,
            default=3,
            help='Number of days before due date to send reminder (default: 3)'
        )

        parser.add_argument(
            '--skip-overdue',
            action='store_true',
            help='Skip sending overdue alerts'
        )

        parser.add_argument(
            '--skip-reminders',
            action='store_true',
            help='Skip sending payment reminders'
        )

        parser.add_argument(
            '--skip-expiring',
            action='store_true',
            help='Skip checking expiring subscriptions'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting subscription alerts check...'))

        reminder_days = options['reminder_days']

        # 1. Check and send overdue invoice alerts
        if not options['skip_overdue']:
            self.stdout.write('\n=== Checking Overdue Invoices ===')
            overdue_invoices = check_overdue_invoices()

            if overdue_invoices:
                self.stdout.write(f'Found {len(overdue_invoices)} overdue invoices')

                sent_count = 0
                failed_count = 0

                for invoice in overdue_invoices:
                    try:
                        if send_overdue_alert(invoice):
                            sent_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✓ Sent overdue alert for invoice {invoice.invoice_number} '
                                    f'(Client: {invoice.subscription.client.company_name})'
                                )
                            )
                        else:
                            failed_count += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f'✗ Failed to send alert for invoice {invoice.invoice_number}'
                                )
                            )
                    except Exception as e:
                        failed_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'✗ Error sending alert for invoice {invoice.invoice_number}: {str(e)}'
                            )
                        )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nOverdue Alerts Summary: {sent_count} sent, {failed_count} failed'
                    )
                )
            else:
                self.stdout.write('No overdue invoices found')

        # 2. Check and send payment reminders
        if not options['skip_reminders']:
            self.stdout.write('\n=== Checking Upcoming Due Invoices ===')
            upcoming_invoices = check_upcoming_due_invoices(reminder_days)

            if upcoming_invoices:
                self.stdout.write(f'Found {len(upcoming_invoices)} invoices due in {reminder_days} days')

                sent_count = 0
                failed_count = 0

                for invoice in upcoming_invoices:
                    try:
                        if send_invoice_reminder(invoice, reminder_days):
                            sent_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✓ Sent reminder for invoice {invoice.invoice_number} '
                                    f'(Client: {invoice.subscription.client.company_name})'
                                )
                            )
                        else:
                            failed_count += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f'✗ Failed to send reminder for invoice {invoice.invoice_number}'
                                )
                            )
                    except Exception as e:
                        failed_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'✗ Error sending reminder for invoice {invoice.invoice_number}: {str(e)}'
                            )
                        )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nPayment Reminders Summary: {sent_count} sent, {failed_count} failed'
                    )
                )
            else:
                self.stdout.write(f'No invoices due in {reminder_days} days')

        # 3. Check expiring subscriptions
        if not options['skip_expiring']:
            self.stdout.write('\n=== Checking Expiring Subscriptions ===')
            from datetime import timedelta

            threshold_date = timezone.now().date() + timedelta(days=7)

            expiring_subscriptions = ClientSubscription.objects.filter(
                status__in=['Active', 'Trial'],
                end_date__lte=threshold_date,
                end_date__gte=timezone.now().date()
            )

            if expiring_subscriptions.exists():
                self.stdout.write(f'Found {expiring_subscriptions.count()} subscriptions expiring within 7 days:')

                for subscription in expiring_subscriptions:
                    days_left = (subscription.end_date - timezone.now().date()).days
                    self.stdout.write(
                        self.style.WARNING(
                            f'  - {subscription.client.company_name}: '
                            f'{subscription.plan.name} expires in {days_left} days '
                            f'(End Date: {subscription.end_date})'
                        )
                    )
            else:
                self.stdout.write('No subscriptions expiring within 7 days')

            # Check already expired subscriptions
            expired_subscriptions = ClientSubscription.objects.filter(
                status='Active',
                end_date__lt=timezone.now().date()
            )

            if expired_subscriptions.exists():
                self.stdout.write(
                    self.style.ERROR(
                        f'\n⚠ WARNING: {expired_subscriptions.count()} subscriptions have expired but are still marked as Active!'
                    )
                )

                for subscription in expired_subscriptions:
                    self.stdout.write(
                        self.style.ERROR(
                            f'  - {subscription.client.company_name}: '
                            f'{subscription.plan.name} expired on {subscription.end_date}'
                        )
                    )

                # Auto-update expired subscriptions
                updated_count = expired_subscriptions.update(status='Expired')
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Updated {updated_count} expired subscriptions to "Expired" status'
                    )
                )

        self.stdout.write(self.style.SUCCESS('\n✓ Subscription alerts check completed!'))