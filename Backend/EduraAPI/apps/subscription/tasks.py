from celery import shared_task
from .utils import (
    check_overdue_invoices,
    send_overdue_alert,
    check_upcoming_due_invoices,
    send_invoice_reminder
)

@shared_task
def check_and_send_overdue_alerts():
    overdue_invoices = check_overdue_invoices()
    for invoice in overdue_invoices:
        send_overdue_alert(invoice)
    return len(overdue_invoices)

@shared_task
def check_and_send_reminders(days_before=3):
    upcoming_invoices = check_upcoming_due_invoices(days_before)
    for invoice in upcoming_invoices:
        send_invoice_reminder(invoice, days_before)
    return len(upcoming_invoices)