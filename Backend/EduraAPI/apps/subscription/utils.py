"""
Utility functions for invoice PDF generation and alert management
"""
from django.core.files.base import ContentFile
from django.utils import timezone
from django.conf import settings
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from io import BytesIO
from datetime import timedelta
import os


def generate_invoice_pdf(invoice_id):
    """
    Generate PDF for an invoice
    """
    from .models import SubscriptionInvoice

    try:
        invoice = SubscriptionInvoice.objects.get(id=invoice_id)
    except SubscriptionInvoice.DoesNotExist:
        raise ValueError(f"Invoice with ID {invoice_id} does not exist")

    # Create PDF buffer
    buffer = BytesIO()

    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )

    # Container for the 'Flowable' objects
    elements = []

    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#333333'),
        spaceAfter=12,
    )

    normal_style = styles["Normal"]
    normal_style.fontSize = 10

    # Add company logo/header (if exists)
    # elements.append(Image('path/to/logo.png', width=2*inch, height=1*inch))
    # elements.append(Spacer(1, 12))

    # Invoice Title
    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Spacer(1, 12))

    # Invoice Details Table
    invoice_info = [
        ['Invoice Number:', invoice.invoice_number],
        ['Invoice Date:', invoice.issue_date.strftime('%B %d, %Y')],
        ['Due Date:', invoice.due_date.strftime('%B %d, %Y')],
        ['Status:', invoice.status.upper()],
    ]

    if invoice.paid_date:
        invoice_info.append(['Paid Date:', invoice.paid_date.strftime('%B %d, %Y')])

    invoice_table = Table(invoice_info, colWidths=[2 * inch, 3 * inch])
    invoice_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))

    elements.append(invoice_table)
    elements.append(Spacer(1, 24))

    # Bill To Section
    elements.append(Paragraph("Bill To:", heading_style))

    client = invoice.subscription.client
    bill_to_info = [
        [Paragraph(f"<b>{client.company_name}</b>", normal_style)],
        [Paragraph(client.auth_user.email, normal_style)],
    ]

    # Add client address if available
    if hasattr(client, 'address') and client.address:
        bill_to_info.append([Paragraph(client.address, normal_style)])

    bill_to_table = Table(bill_to_info, colWidths=[5 * inch])
    bill_to_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    elements.append(bill_to_table)
    elements.append(Spacer(1, 24))

    # Invoice Items Table
    elements.append(Paragraph("Invoice Details:", heading_style))

    # Table header
    data = [
        ['Description', 'Quantity', 'Unit Price', 'Total'],
    ]

    # Add invoice items
    items = invoice.get_invoice_items()
    for item in items:
        data.append([
            item['description'],
            str(item['quantity']),
            f"${item['unit_price']:.2f}",
            f"${item['total']:.2f}"
        ])

    # Add subtotal, tax, and total
    data.append(['', '', 'Subtotal:', f"${invoice.amount:.2f}"])

    if invoice.discount_amount > 0:
        data.append(['', '', 'Discount:', f"-${invoice.discount_amount:.2f}"])

    if invoice.tax_amount > 0:
        data.append(['', '', f'Tax ({invoice.subscription.plan.tax_rate}%):', f"${invoice.tax_amount:.2f}"])

    data.append(['', '', 'Total Amount:', f"${invoice.total_amount:.2f}"])

    # Create table
    items_table = Table(data, colWidths=[3 * inch, 1 * inch, 1.5 * inch, 1.5 * inch])
    items_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A90E2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

        # Data rows
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 1), (-1, -4), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -4), 1, colors.grey),

        # Summary rows (last 3 or 4 rows)
        ('FONTNAME', (2, -3), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (2, -3), (-1, -3), 1, colors.black),
        ('LINEABOVE', (2, -1), (-1, -1), 2, colors.black),
        ('BACKGROUND', (2, -1), (-1, -1), colors.HexColor('#f0f0f0')),
    ]))

    elements.append(items_table)
    elements.append(Spacer(1, 24))

    # Payment Instructions
    elements.append(Paragraph("Payment Instructions:", heading_style))
    payment_instructions = f"""
    Please make payment by {invoice.due_date.strftime('%B %d, %Y')}.<br/>
    Payment Method: {invoice.subscription.payment_method or 'As per agreement'}<br/>
    Currency: {invoice.currency}
    """
    elements.append(Paragraph(payment_instructions, normal_style))
    elements.append(Spacer(1, 24))

    # Notes section
    if invoice.notes:
        elements.append(Paragraph("Notes:", heading_style))
        elements.append(Paragraph(invoice.notes, normal_style))
        elements.append(Spacer(1, 24))

    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER,
    )

    elements.append(Spacer(1, 48))
    elements.append(Paragraph("Thank you for your business!", footer_style))
    elements.append(Paragraph("This is a computer-generated invoice.", footer_style))

    # Build PDF
    doc.build(elements)

    # Get PDF content
    pdf_content = buffer.getvalue()
    buffer.close()

    # Save PDF to invoice
    pdf_filename = f"invoice_{invoice.invoice_number}.pdf"
    invoice.pdf_file.save(pdf_filename, ContentFile(pdf_content), save=True)
    invoice.pdf_generated_at = timezone.now()
    invoice.save(update_fields=['pdf_file', 'pdf_generated_at'])

    return invoice


def check_overdue_invoices():
    """
    Check for overdue invoices and send alerts
    Returns list of overdue invoices
    """
    from .models import SubscriptionInvoice

    now = timezone.now().date()

    # Get overdue invoices that haven't been marked as overdue yet
    overdue_invoices = SubscriptionInvoice.objects.filter(
        status__in=['Sent', 'Draft'],
        due_date__lt=now
    )

    # Update status to overdue
    updated_count = overdue_invoices.update(status='Overdue')

    # Get invoices for alert sending
    invoices_for_alert = SubscriptionInvoice.objects.filter(
        status='Overdue',
        overdue_alert_sent=False
    )

    return list(invoices_for_alert)


def send_overdue_alert(invoice):
    """
    Send overdue alert for an invoice
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string

    try:
        client = invoice.subscription.client

        subject = f"Invoice Overdue - {invoice.invoice_number}"

        # Email content
        message = f"""
Dear {client.company_name},

This is a reminder that your invoice {invoice.invoice_number} is now overdue.

Invoice Details:
- Invoice Number: {invoice.invoice_number}
- Amount Due: ${invoice.total_amount}
- Due Date: {invoice.due_date.strftime('%B %d, %Y')}
- Days Overdue: {invoice.days_overdue()}

Please make payment at your earliest convenience to avoid service interruption.

If you have already made payment, please disregard this message.

Thank you,
Subscription Management Team
        """

        # Send email
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[client.auth_user.email],
            fail_silently=False,
        )

        # Mark alert as sent
        invoice.overdue_alert_sent = True
        invoice.overdue_alert_sent_at = timezone.now()
        invoice.save(update_fields=['overdue_alert_sent', 'overdue_alert_sent_at'])

        return True

    except Exception as e:
        print(f"Error sending overdue alert for invoice {invoice.id}: {str(e)}")
        return False


def send_invoice_reminder(invoice, days_before=3):
    """
    Send invoice payment reminder before due date
    """
    from django.core.mail import send_mail

    try:
        client = invoice.subscription.client

        subject = f"Payment Reminder - Invoice {invoice.invoice_number}"

        message = f"""
Dear {client.company_name},

This is a friendly reminder that your invoice {invoice.invoice_number} is due in {days_before} days.

Invoice Details:
- Invoice Number: {invoice.invoice_number}
- Amount Due: ${invoice.total_amount}
- Due Date: {invoice.due_date.strftime('%B %d, %Y')}

Please ensure payment is made before the due date.

Thank you,
Subscription Management Team
        """

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[client.auth_user.email],
            fail_silently=False,
        )

        # Mark reminder as sent
        invoice.reminder_sent = True
        invoice.reminder_sent_at = timezone.now()
        invoice.save(update_fields=['reminder_sent', 'reminder_sent_at'])

        return True

    except Exception as e:
        print(f"Error sending reminder for invoice {invoice.id}: {str(e)}")
        return False


def check_upcoming_due_invoices(days_before=3):
    """
    Check for invoices due soon and send reminders
    """
    from .models import SubscriptionInvoice

    target_date = timezone.now().date() + timedelta(days=days_before)

    # Get invoices due in X days that haven't had reminder sent
    upcoming_invoices = SubscriptionInvoice.objects.filter(
        status='Sent',
        due_date=target_date,
        reminder_sent=False
    )

    return list(upcoming_invoices)


def get_invoice_statistics():
    """
    Get invoice statistics for dashboard
    """
    from .models import SubscriptionInvoice
    from django.db.models import Sum, Count, Q

    now = timezone.now().date()

    stats = {
        'total_invoices': SubscriptionInvoice.objects.count(),
        'paid_invoices': SubscriptionInvoice.objects.filter(status='Paid').count(),
        'overdue_invoices': SubscriptionInvoice.objects.filter(status='Overdue').count(),
        'pending_invoices': SubscriptionInvoice.objects.filter(status__in=['Sent', 'Draft']).count(),
        'total_amount_due': SubscriptionInvoice.objects.filter(
            status__in=['Sent', 'Overdue']
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        'total_amount_paid': SubscriptionInvoice.objects.filter(
            status='Paid'
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
    }

    return stats


def regenerate_invoice_pdf(invoice_id):
    """
    Regenerate PDF for an existing invoice
    """
    from .models import SubscriptionInvoice

    try:
        invoice = SubscriptionInvoice.objects.get(id=invoice_id)

        # Delete old PDF if exists
        if invoice.pdf_file:
            invoice.pdf_file.delete(save=False)

        # Generate new PDF
        return generate_invoice_pdf(invoice_id)

    except SubscriptionInvoice.DoesNotExist:
        raise ValueError(f"Invoice with ID {invoice_id} does not exist")