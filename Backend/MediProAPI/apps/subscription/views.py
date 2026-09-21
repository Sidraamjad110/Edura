from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.http import FileResponse
from datetime import timedelta
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from ..users.models import CustomUser
from .models import SubscriptionPlan,ClientSubscription, SubscriptionInvoice, SubscriptionType
from .serializers import (
    SubscriptionPlanSerializer,
    SubscriptionPlanCreateUpdateSerializer,
    ClientSubscriptionSerializer,
    ClientSubscriptionCreateSerializer,
    ClientSubscriptionUpdateSerializer,
    SubscriptionActivateSerializer,
SubscriptionTypeSerializer,
    SubscriptionEndSerializer,
    SubscriptionInvoiceSerializer,
    ClientWithSubscriptionSerializer,
)
from .utils import (
    generate_invoice_pdf,
    check_overdue_invoices,
    send_overdue_alert,
    send_invoice_reminder,
    check_upcoming_due_invoices,
    get_invoice_statistics,
    regenerate_invoice_pdf
)
from .services.access import activate_emergency_grace, reset_usage_on_activation
from .services.usage import build_access_status
from .services.client_overview import build_client_subscription_overview

User = get_user_model()


# ================ SUBSCRIPTION PLAN CRUD VIEWS ================

@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def subscription_plan_list(request):
    """Get all subscription plans with filtering"""
    # is_active = request.GET.get('is_active')
    tier = request.GET.get('tier')
    search = request.GET.get('search')
    # show_all = request.GET.get('show_all', 'false').lower() == 'true'

    plans = SubscriptionPlan.objects.all()

    # if not show_all and is_active is None:
    #     plans = plans.filter(is_active=True)
    # elif is_active:
    #     is_active_bool = is_active.lower() == 'true'
    #     plans = plans.filter(is_active=is_active_bool)

    if tier:
        plans = plans.filter(tier=tier)

    if search:
        plans = plans.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search) |
            Q(tier__icontains=search)
        )

    plans = plans.order_by('sort_order', 'price')

    # Serialize plans
    plan_serializer = SubscriptionPlanSerializer(plans, many=True)

    # Get subscription types and serialize them
    subscription_types = SubscriptionType.objects.all()
    type_serializer = SubscriptionTypeSerializer(subscription_types, many=True)
    payment_statuses = [choice[0] for choice in ClientSubscription.PAYMENT_STATUS_CHOICES]

    return Response({
        "success": True,
        "message": "Subscription plans retrieved successfully",
        "data": {
            "plans": plan_serializer.data,
            "subscription_types": type_serializer.data,
            "payment_options": payment_statuses
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_plan_detail(request, plan_id):
    """Get single subscription plan details"""
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return Response({
            "success": False,
            "message": "Subscription plan not found"
        }, status=status.HTTP_404_NOT_FOUND)

    serializer = SubscriptionPlanSerializer(plan)
    return Response({
        "success": True,
        "message": "Subscription plan retrieved successfully",
        "data": serializer.data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def subscription_plan_set_active_status(request):
    """Set subscription plan active status using RoleGroup logic pattern"""
    plan_id = request.data.get('plan_id')
    is_active = request.data.get('is_active')

    # 1. Validate required fields
    if not plan_id:
        return Response({
            "success": False,
            "message": "plan_id is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    if is_active is None:
        return Response({
            "success": False,
            "message": "is_active is required"
        }, status=status.HTTP_400_BAD_REQUEST)

    # 2. Convert is_active to boolean
    try:
        is_active_bool = str(is_active).lower() == 'true'
    except Exception:
        return Response({
            "success": False,
            "message": "is_active must be true or false"
        }, status=status.HTTP_400_BAD_REQUEST)

    # 3. Manual lookup with DoesNotExist handling
    try:
        plan = SubscriptionPlan.objects.get(pk=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return Response({
            "success": False,
            "message": "Subscription plan not found"
        }, status=status.HTTP_404_NOT_FOUND)

    # 4. Logical constraint: Check for active dependencies before deactivating
    if plan.is_active and not is_active_bool:
        # Check if the plan is currently tied to any active client subscriptions
        if ClientSubscription.objects.filter(plan=plan, status='active').exists():
            return Response({
                "success": False,
                "message": "Cannot deactivate plan because it is currently assigned to active subscribers"
            }, status=status.HTTP_400_BAD_REQUEST)

    # 5. Update the status
    plan.is_active = is_active_bool
    plan.save()

    status_text = "activated" if plan.is_active else "deactivated"
    return Response({
        "success": True,
        "message": f"Subscription plan {status_text} successfully",
        "data": {
            "plan_id": plan.id,
            "plan_name": plan.name,
            "is_active": plan.is_active
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def subscription_plan_create(request):
    """Create new subscription plan (only superuser)"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to create subscription plans"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = SubscriptionPlanCreateUpdateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        plan = serializer.save()
        full_serializer = SubscriptionPlanSerializer(plan)
        return Response({
            "success": True,
            "message": "Subscription plan created successfully",
            "data": full_serializer.data
        }, status=status.HTTP_201_CREATED)

    return Response({
        "success": False,
        "message": "Validation failed",
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def subscription_plan_update(request, plan_id):
    """Update subscription plan (only superuser)"""
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return Response({
            "success": False,
            "message": "Subscription plan not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to update subscription plans"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = SubscriptionPlanCreateUpdateSerializer(plan, data=request.data, partial=True)
    if serializer.is_valid():
        plan = serializer.save()
        full_serializer = SubscriptionPlanSerializer(plan)
        return Response({
            "success": True,
            "message": "Subscription plan updated successfully",
            "data": full_serializer.data
        })

    return Response({
        "success": False,
        "message": "Validation failed",
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def subscription_plan_delete(request, plan_id):
    """Delete subscription plan (only superuser)"""
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return Response({
            "success": False,
            "message": "Subscription plan not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to delete subscription plans"
        }, status=status.HTTP_403_FORBIDDEN)

    # 1. Check for TRULY active users.
    # We exclude 'Cancelled' and 'Pending' if they are just leftover records.
    active_subscriptions = plan.client_subscriptions.filter(
        status__in=['Active', 'Trial']
    ).exists()

    if active_subscriptions:
        return Response({
            "success": False,
            "message": "Cannot delete plan with active subscriptions. Deactivate instead."
        }, status=status.HTTP_400_BAD_REQUEST)

    # 2. Use an atomic transaction to clean up orphaned records and delete the plan
    try:
        with transaction.atomic():
            plan.client_subscriptions.all().delete()
            plan.delete()

        return Response({
            "success": True,
            "message": "Subscription plan and associated history deleted successfully"
        })
    except Exception as e:
        return Response({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def subscription_assign(request):
    """Assign subscription plan to client"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to assign subscriptions"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = ClientSubscriptionCreateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        subscription = serializer.save()
        payment_status = request.data.get('payment_status') or 'Paid'
        subscription.payment_status = payment_status
        # Adjust amount based on subscription_type
        if subscription.subscription_type_id == 1:  # Monthly
            subscription.amount = subscription.plan.get_monthly_price()*1
        elif subscription.subscription_type_id == 2:  # Yearly
            subscription.amount = subscription.plan.get_monthly_price() * 12

        # Activate subscription immediately if not a trial

        subscription.status = 'Active'
        reset_usage_on_activation(subscription)
        subscription.save()

        modules_result = None
        try:
            from .services.plan_modules import assign_plan_modules_to_client
            modules_result = assign_plan_modules_to_client(subscription.client, subscription.plan)
        except Exception as exc:
            modules_result = {'error': str(exc)}

        # Return full subscription with subscription_type_id
        full_serializer = ClientSubscriptionSerializer(subscription, context={'request': request})
        return Response({
            "success": True,
            "message": "Subscription assigned successfully. Invoice will be generated automatically.",
            "data": full_serializer.data,
            "modules_assigned": modules_result,
        }, status=status.HTTP_201_CREATED)

    return Response({
        "success": False,
        "message": "Validation failed",
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def update_payment_status(request):
    """
    Update payment status for a client subscription.
    Frontend sends client_id, optional plan_id, and new payment_status.
    """
    client_id = request.data.get('user_id')  # Now this is actually client_id
    plan_id = request.data.get('plan_id')
    new_status = request.data.get('payment_status')

    print("REQUEST DATA:", request.data)
    print("CLIENT ID:", client_id)
    print("PLAN ID:", plan_id)
    print("NEW STATUS:", new_status)

    # Security check
    if not request.user.is_superuser:
        return Response({"success": False, "message": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

    if not client_id or not new_status:
        return Response({"success": False, "message": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

    # Lookup subscription using client_id directly (no need to look up client)
    if plan_id:
        subscription = ClientSubscription.objects.filter(
            client_id=client_id,  # Direct filter using client_id
            plan_id=plan_id
        ).first()
    else:
        subscription = ClientSubscription.objects.filter(
            client_id=client_id  # Direct filter using client_id
        ).order_by('-created_at').first()

    if not subscription:
        return Response({
            "success": False,
            "message": "No subscription found for this client with the given plan."
        }, status=status.HTTP_404_NOT_FOUND)

    subscription.payment_status = new_status
    subscription.save()

    return Response({
        "success": True,
        "message": f"Payment status updated to {new_status}",
        "subscription_id": subscription.id,
        "status": subscription.status,
        "payment_status": subscription.payment_status
    }, status=status.HTTP_200_OK)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def trial_subscription_create(request):
    """Create trial subscription for client"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to create trial subscriptions"
        }, status=status.HTTP_403_FORBIDDEN)


    serializer = ClientSubscriptionCreateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        subscription = serializer.save()
        reset_usage_on_activation(subscription)
        modules_result = None
        try:
            from .services.plan_modules import assign_plan_modules_to_client
            modules_result = assign_plan_modules_to_client(subscription.client, subscription.plan)
        except Exception as exc:
            modules_result = {'error': str(exc)}
        full_serializer = ClientSubscriptionSerializer(subscription, context={'request': request})
        return Response({
            "success": True,
            "message": "Trial subscription created successfully",
            "data": full_serializer.data,
            "modules_assigned": modules_result,
        }, status=status.HTTP_201_CREATED)

    return Response({
        "success": False,
        "message": "Validation failed",
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_subscription_detail(request, client_id):
    """Get client's subscription details"""
    from MediProAPI.apps.users.models import Client

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return Response({
            "success": False,
            "message": "Client not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not (request.user.is_superuser or
            (hasattr(request.user, 'client_profile') and request.user.client_profile == client)):
        return Response({
            "success": False,
            "message": "You do not have permission to view this subscription"
        }, status=status.HTTP_403_FORBIDDEN)

    active_subscription = client.subscriptions.filter(
        status__in=['Active', 'Trial']
    ).first()

    if not active_subscription:
        return Response({
            "success": True,
            "message": "No active subscription found",
            "data": None
        })

    serializer = ClientSubscriptionSerializer(active_subscription, context={'request': request})
    return Response({
        "success": True,
        "message": "Subscription retrieved successfully",
        "data": serializer.data
    })


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def subscription_activate(request, subscription_id):
    """Activate subscription"""
    try:
        subscription = ClientSubscription.objects.get(id=subscription_id)
    except ClientSubscription.DoesNotExist:
        return Response({
            "success": False,
            "message": "Subscription not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to activate subscriptions"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = SubscriptionActivateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            "success": False,
            "message": "Validation failed",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    # if subscription.is_trial and subscription.trial_end_date:
    #     subscription.status = 'Trial'
    # else:
    #     subscription.status = 'Active'

    payment_method = serializer.validated_data.get('payment_method')
    stripe_payment_intent_id = serializer.validated_data.get('stripe_payment_intent_id')

    if payment_method:
        subscription.payment_method = payment_method
    if stripe_payment_intent_id:
        subscription.payment_status = 'Paid'

    if subscription.status in ('Active', 'Trial'):
        reset_usage_on_activation(subscription)
    subscription.save()

    full_serializer = ClientSubscriptionSerializer(subscription, context={'request': request})
    return Response({
        "success": True,
        "message": "Subscription activated successfully",
        "data": full_serializer.data
    })


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def subscription_end(request, subscription_id):
    """End subscription (with reason)"""
    try:
        subscription = ClientSubscription.objects.get(id=subscription_id)
    except ClientSubscription.DoesNotExist:
        return Response({
            "success": False,
            "message": "Subscription not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to end subscriptions"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = SubscriptionEndSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            "success": False,
            "message": "Validation failed",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    reason = serializer.validated_data.get('reason')
    immediate = serializer.validated_data.get('immediate', False)

    subscription.status = 'Cancelled'
    subscription.cancellation_reason = reason
    subscription.cancelled_at = timezone.now()
    subscription.auto_renew = False

    if immediate:
        subscription.end_date = timezone.now().date()

    subscription.save()

    full_serializer = ClientSubscriptionSerializer(subscription, context={'request': request})
    return Response({
        "success": True,
        "message": "Subscription ended successfully",
        "data": full_serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_list(request):
    """List all subscriptions with filters"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to view all subscriptions"
        }, status=status.HTTP_403_FORBIDDEN)

    client_id = request.GET.get('client_id')
    plan_id = request.GET.get('plan_id')
    status_filter = request.GET.get('status')
    billing_cycle = request.GET.get('billing_cycle')
    payment_status = request.GET.get('payment_status')
    search = request.GET.get('search')

    subscriptions = ClientSubscription.objects.all().select_related(
        'client', 'plan', 'client__auth_user'
    )

    if client_id:
        subscriptions = subscriptions.filter(client_id=client_id)

    if plan_id:
        subscriptions = subscriptions.filter(plan_id=plan_id)

    if status_filter:
        subscriptions = subscriptions.filter(status=status_filter)

    if billing_cycle:
        subscriptions = subscriptions.filter(billing_cycle=billing_cycle)

    if payment_status:
        subscriptions = subscriptions.filter(payment_status=payment_status)

    if search:
        subscriptions = subscriptions.filter(
            Q(client__company_name__icontains=search) |
            Q(client__auth_user__email__icontains=search) |
            Q(plan__name__icontains=search)
        )

    subscriptions = subscriptions.order_by('-created_at')

    serializer = ClientSubscriptionSerializer(subscriptions, many=True, context={'request': request})
    return Response({
        "success": True,
        "message": "Subscriptions retrieved successfully",
        "data": serializer.data
    })


# ================ INVOICE VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def subscription_invoices(request, subscription_id):
    """Get all invoices for a subscription"""
    try:
        subscription = ClientSubscription.objects.get(id=subscription_id)
    except ClientSubscription.DoesNotExist:
        return Response({
            "success": False,
            "message": "Subscription not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not (request.user.is_superuser or
            (hasattr(request.user, 'client_profile') and request.user.client_profile == subscription.client)):
        return Response({
            "success": False,
            "message": "You do not have permission to view these invoices"
        }, status=status.HTTP_403_FORBIDDEN)

    invoices = subscription.invoices.all().order_by('-issue_date')
    serializer = SubscriptionInvoiceSerializer(invoices, many=True, context={'request': request})

    return Response({
        "success": True,
        "message": "Invoices retrieved successfully",
        "data": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_invoices(request, client_id):
    """Get all invoices for a client"""
    from MediProAPI.apps.users.models import Client

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return Response({
            "success": False,
            "message": "Client not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not (request.user.is_superuser or
            (hasattr(request.user, 'client_profile') and request.user.client_profile == client)):
        return Response({
            "success": False,
            "message": "You do not have permission to view these invoices"
        }, status=status.HTTP_403_FORBIDDEN)

    invoices = SubscriptionInvoice.objects.filter(
        subscription__client=client
    ).select_related('subscription', 'subscription__plan').order_by('-issue_date')

    serializer = SubscriptionInvoiceSerializer(invoices, many=True, context={'request': request})

    return Response({
        "success": True,
        "message": "Client invoices retrieved successfully",
        "data": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def invoice_detail(request, invoice_id):
    """Get single invoice details"""
    try:
        invoice = SubscriptionInvoice.objects.get(id=invoice_id)
    except SubscriptionInvoice.DoesNotExist:
        return Response({
            "success": False,
            "message": "Invoice not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not (request.user.is_superuser or
            (hasattr(request.user, 'client_profile') and
             request.user.client_profile == invoice.subscription.client)):
        return Response({
            "success": False,
            "message": "You do not have permission to view this invoice"
        }, status=status.HTTP_403_FORBIDDEN)

    serializer = SubscriptionInvoiceSerializer(invoice, context={'request': request})
    return Response({
        "success": True,
        "message": "Invoice retrieved successfully",
        "data": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def invoice_download_pdf(request, invoice_id):
    """Download invoice PDF"""
    try:
        invoice = SubscriptionInvoice.objects.get(id=invoice_id)
    except SubscriptionInvoice.DoesNotExist:
        return Response({
            "success": False,
            "message": "Invoice not found"
        }, status=status.HTTP_404_NOT_FOUND)

    if not (request.user.is_superuser or
            (hasattr(request.user, 'client_profile') and
             request.user.client_profile == invoice.subscription.client)):
        return Response({
            "success": False,
            "message": "You do not have permission to download this invoice"
        }, status=status.HTTP_403_FORBIDDEN)

    # Generate PDF if not exists
    if not invoice.pdf_file:
        try:
            generate_invoice_pdf(invoice_id)
            invoice.refresh_from_db()
        except Exception as e:
            return Response({
                "success": False,
                "message": f"Error generating PDF: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if invoice.pdf_file:
        response = FileResponse(invoice.pdf_file.open('rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
        return response
    else:
        return Response({
            "success": False,
            "message": "PDF file not available"
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def invoice_regenerate_pdf(request, invoice_id):
    """Regenerate invoice PDF (admin only)"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to regenerate invoice PDFs"
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        invoice = regenerate_invoice_pdf(invoice_id)
        serializer = SubscriptionInvoiceSerializer(invoice, context={'request': request})
        return Response({
            "success": True,
            "message": "Invoice PDF regenerated successfully",
            "data": serializer.data
        })
    except Exception as e:
        return Response({
            "success": False,
            "message": f"Error regenerating PDF: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def invoice_mark_paid(request, invoice_id):
    """Mark invoice as paid (admin only)"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to update invoice status"
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        invoice = SubscriptionInvoice.objects.get(id=invoice_id)
    except SubscriptionInvoice.DoesNotExist:
        return Response({
            "success": False,
            "message": "Invoice not found"
        }, status=status.HTTP_404_NOT_FOUND)

    invoice.status = 'Paid'
    invoice.paid_date = timezone.now().date()
    invoice.save()

    # Update subscription payment status
    invoice.subscription.payment_status = 'Paid'
    invoice.subscription.save()

    serializer = SubscriptionInvoiceSerializer(invoice, context={'request': request})
    return Response({
        "success": True,
        "message": "Invoice marked as paid successfully",
        "data": serializer.data
    })


# ================ ALERT & REPORTING VIEWS ================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def overdue_invoices(request):
    """Get all overdue invoices"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to view overdue invoices"
        }, status=status.HTTP_403_FORBIDDEN)

    # Check and update overdue invoices
    overdue_list = check_overdue_invoices()

    # Get all overdue invoices
    invoices = SubscriptionInvoice.objects.filter(
        status='Overdue'
    ).select_related('subscription', 'subscription__client', 'subscription__plan')

    serializer = SubscriptionInvoiceSerializer(invoices, many=True, context={'request': request})

    return Response({
        "success": True,
        "message": "Overdue invoices retrieved successfully",
        "data": serializer.data,
        "total_overdue": invoices.count()
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def send_overdue_alerts(request):
    """Send alerts for overdue invoices (admin only)"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to send alerts"
        }, status=status.HTTP_403_FORBIDDEN)

    overdue_list = check_overdue_invoices()

    sent_count = 0
    failed_count = 0

    for invoice in overdue_list:
        if send_overdue_alert(invoice):
            sent_count += 1
        else:
            failed_count += 1

    return Response({
        "success": True,
        "message": f"Sent {sent_count} alerts successfully, {failed_count} failed",
        "data": {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total_overdue": len(overdue_list)
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def send_invoice_reminders(request):
    """Send reminders for upcoming due invoices (admin only)"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to send reminders"
        }, status=status.HTTP_403_FORBIDDEN)

    days_before = int(request.GET.get('days', 3))
    upcoming_list = check_upcoming_due_invoices(days_before)

    sent_count = 0
    failed_count = 0

    for invoice in upcoming_list:
        if send_invoice_reminder(invoice, days_before):
            sent_count += 1
        else:
            failed_count += 1

    return Response({
        "success": True,
        "message": f"Sent {sent_count} reminders successfully, {failed_count} failed",
        "data": {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total_upcoming": len(upcoming_list)
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def invoice_statistics(request):
    """Get invoice statistics"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to view statistics"
        }, status=status.HTTP_403_FORBIDDEN)

    stats = get_invoice_statistics()

    return Response({
        "success": True,
        "message": "Invoice statistics retrieved successfully",
        "data": stats
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def expiring_subscriptions(request):
    """Get expiring subscriptions (for alerts)"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to view expiring subscriptions"
        }, status=status.HTTP_403_FORBIDDEN)

    days_threshold = int(request.GET.get('days', 7))
    threshold_date = timezone.now().date() + timedelta(days=days_threshold)

    expiring_subscriptions = ClientSubscription.objects.filter(
        status__in=['Active', 'Trial'],
        end_date__lte=threshold_date,
        end_date__gte=timezone.now().date()
    ).select_related('client', 'plan', 'client__auth_user')

    expired_subscriptions = ClientSubscription.objects.filter(
        status='Active',
        end_date__lt=timezone.now().date()
    ).select_related('client', 'plan', 'client__auth_user')

    expiring_serializer = ClientSubscriptionSerializer(expiring_subscriptions, many=True, context={'request': request})
    expired_serializer = ClientSubscriptionSerializer(expired_subscriptions, many=True, context={'request': request})

    return Response({
        "success": True,
        "message": "Expiring subscriptions retrieved successfully",
        "data": {
            "expiring_soon": expiring_serializer.data,
            "expired": expired_serializer.data,
            "threshold_days": days_threshold,
            "total_expiring_soon": expiring_subscriptions.count(),
            "total_expired": expired_subscriptions.count(),
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def clients_with_subscriptions(request):
    """List all clients with their subscription info"""
    if not request.user.is_superuser:
        return Response({
            "success": False,
            "message": "You do not have permission to view client subscriptions"
        }, status=status.HTTP_403_FORBIDDEN)

    from MediProAPI.apps.users.models import Client

    has_subscription = request.GET.get('has_subscription')
    plan_tier = request.GET.get('plan_tier')
    subscription_status = request.GET.get('subscription_status')
    search = request.GET.get('search')

    clients = Client.objects.all().select_related('auth_user').prefetch_related('subscriptions')

    if search:
        clients = clients.filter(
            Q(company_name__icontains=search) |
            Q(auth_user__email__icontains=search) |
            Q(auth_user__username__icontains=search)
        )

    if has_subscription:
        has_sub_bool = has_subscription.lower() == 'true'
        if has_sub_bool:
            clients = clients.filter(subscriptions__isnull=False).distinct()
        else:
            clients = clients.filter(subscriptions__isnull=True)

    if plan_tier:
        clients = clients.filter(
            subscriptions__plan__tier=plan_tier,
            subscriptions__status__in=['Active', 'Trial']
        ).distinct()

    if subscription_status:
        clients = clients.filter(
            subscriptions__status=subscription_status
        ).distinct()

    clients = clients.order_by('company_name')

    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    start = (page - 1) * page_size
    end = start + page_size

    paginated_clients = clients[start:end]

    serializer = ClientWithSubscriptionSerializer(paginated_clients, many=True)

    return Response({
        "success": True,
        "message": "Clients with subscriptions retrieved successfully",
        "data": serializer.data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": clients.count(),
            "has_next": end < clients.count(),
            "has_previous": page > 1,
        }
    })


def _get_client_or_404(client_id):
    from MediProAPI.apps.users.models import Client

    try:
        return Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return None


def _user_can_access_client_subscription(user, client) -> bool:
    if user.is_superuser:
        return True
    if hasattr(user, "client_profile") and user.client_profile == client:
        return True
    if hasattr(user, "custom_profile") and user.custom_profile.client_id == client.id:
        return True
    return False


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def client_subscription_overview(request, client_id):
    """Full client subscription + plan + real usage from DB tables."""
    client = _get_client_or_404(client_id)
    if not client:
        return Response(
            {"success": False, "message": "Client not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not _user_can_access_client_subscription(request.user, client):
        return Response(
            {"success": False, "message": "You do not have permission to view this subscription"},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = build_client_subscription_overview(client, user=request.user)
    return Response(
        {
            "success": True,
            "message": "Client subscription overview retrieved successfully",
            "data": data,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def client_access_status(request, client_id):
    """Subscription + usage status for portal banner and gating."""
    client = _get_client_or_404(client_id)
    if not client:
        return Response(
            {"success": False, "message": "Client not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not _user_can_access_client_subscription(request.user, client):
        return Response(
            {"success": False, "message": "You do not have permission to view this status"},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = build_access_status(client, user=request.user)
    return Response(
        {
            "success": True,
            "message": "Access status retrieved successfully",
            "data": data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def client_emergency_activate(request, client_id):
    """Enable 24-hour emergency AI access for expired subscriptions (client login only)."""
    client = _get_client_or_404(client_id)
    if not client:
        return Response(
            {"success": False, "message": "Client not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not hasattr(request.user, "client_profile") or request.user.client_profile.id != client.id:
        return Response(
            {
                "success": False,
                "message": "Only the main client account can activate emergency access.",
                "code": "GRACE_FORBIDDEN",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    result = activate_emergency_grace(client, request.user)
    if not result.allowed:
        return Response(
            {
                "success": False,
                "message": result.message,
                "code": result.code,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    status_data = build_access_status(client, user=request.user)
    return Response(
        {
            "success": True,
            "message": result.message,
            "code": result.code,
            "data": status_data,
        }
    )