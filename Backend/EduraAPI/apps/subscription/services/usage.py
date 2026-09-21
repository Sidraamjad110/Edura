"""Usage aggregation for dashboards and access-status API."""

from __future__ import annotations

from EduraAPI.apps.subscription.services.access import (
    _subscription_paid,
    check_ai_access,
    check_upload_access,
    get_client_subscription,
)
from EduraAPI.apps.subscription.services.plan_features import plan_feature_flags
from EduraAPI.apps.users.models import Client, CustomUser


def build_usage_snapshot(client: Client) -> dict:
    subscription = get_client_subscription(client)
    if not subscription or not subscription.plan:
        return {
            "enable_chatbot": False,
            "enable_ai_agent": False,
            "minutes_used": 0,
            "minutes_limit": 0,
            "minutes_remaining": 0,
            "ai_tokens_used": 0,
            "ai_tokens_limit": 0,
            "ai_tokens_remaining": 0,
            "embeddings_used": 0,
            "embeddings_limit": 0,
            "embeddings_remaining": 0,
            "upload_enabled": False,
            "users_count": CustomUser.objects.filter(client=client).count(),
            "user_limit": 0,
            "agents_count": 0,
            "agents_limit": 0,
        }

    plan = subscription.plan
    flags = plan_feature_flags(plan)
    minutes_used = float(subscription.minutes_used or 0)
    minutes_limit = int(plan.minutes_per_month or 0)
    tokens_used = int(subscription.ai_tokens_used or 0)
    tokens_limit = int(plan.ai_tokens_per_month or 0)
    embeddings_used = int(subscription.embeddings_used or 0)
    embeddings_limit = int(plan.embeddings_per_month or 0)
    upload_access = check_upload_access(client)

    return {
        "enable_chatbot": flags["enable_chatbot"],
        "enable_ai_agent": flags["enable_ai_agent"],
        "minutes_used": minutes_used,
        "minutes_limit": minutes_limit,
        "minutes_remaining": max(0, minutes_limit - minutes_used),
        "ai_tokens_used": tokens_used,
        "ai_tokens_limit": tokens_limit,
        "ai_tokens_remaining": max(0, tokens_limit - tokens_used),
        "embeddings_used": embeddings_used,
        "embeddings_limit": embeddings_limit,
        "embeddings_remaining": max(0, embeddings_limit - embeddings_used),
        "upload_enabled": upload_access.allowed,
        "upload_block_reason": upload_access.reason if not upload_access.allowed else None,
        "upload_block_message": upload_access.message if not upload_access.allowed else None,
        "users_count": CustomUser.objects.filter(client=client).count(),
        "user_limit": plan.user_limit,
        "agents_count": 0,
        "agents_limit": 0,
    }


def build_access_status(client: Client, *, user=None) -> dict:
    access = check_ai_access(client, user=user)
    upload_access = check_upload_access(client, user=user)
    subscription = get_client_subscription(client)
    usage = build_usage_snapshot(client)

    sub_valid = False
    days_remaining = 0
    if subscription:
        from django.utils import timezone

        now = timezone.now().date()
        sub_valid = (
            subscription.status in ("Active", "Trial")
            and subscription.start_date <= now <= subscription.end_date
        )
        if subscription.end_date and now <= subscription.end_date:
            days_remaining = (subscription.end_date - now).days

    can_emergency = False
    if subscription and not sub_valid and user and hasattr(user, "client_profile"):
        if user.client_profile.id == client.id and _subscription_paid(subscription):
            can_emergency = True

    return {
        "ai_enabled": access.allowed,
        "upload_enabled": upload_access.allowed,
        "upload_message": upload_access.message if not upload_access.allowed else "",
        "upload_code": upload_access.code if not upload_access.allowed else "",
        "reason": access.reason,
        "message": access.message,
        "code": access.code,
        "can_emergency_activate": can_emergency,
        "grace_active": access.grace_active,
        "grace_ends_at": access.grace_ends_at,
        "subscription_status": subscription.status if subscription else None,
        "payment_status": subscription.payment_status if subscription else None,
        "payment_paid": _subscription_paid(subscription) if subscription else False,
        "plan_name": subscription.plan.name if subscription and subscription.plan else None,
        "plan_tier": subscription.plan.tier if subscription and subscription.plan else None,
        "billing_cycle": subscription.billing_cycle if subscription else None,
        "start_date": subscription.start_date.isoformat() if subscription and subscription.start_date else None,
        "end_date": subscription.end_date.isoformat() if subscription and subscription.end_date else None,
        "next_billing_date": (
            subscription.next_billing_date.isoformat()
            if subscription and subscription.next_billing_date
            else None
        ),
        "amount": float(subscription.amount) if subscription and subscription.amount is not None else None,
        "currency": subscription.currency if subscription else None,
        "days_remaining": days_remaining,
        "usage": usage,
    }
