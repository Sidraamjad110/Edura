"""Client subscription overview built from real DB tables."""

from __future__ import annotations

from django.utils import timezone

from EduraAPI.apps.subscription.models import ClientSubscription
from EduraAPI.apps.subscription.services.access import get_client_subscription
from EduraAPI.apps.subscription.services.usage import build_access_status
from EduraAPI.apps.users.models import Client, CustomUser


def _billing_period_bounds(subscription: ClientSubscription) -> tuple:
    """Subscription billing window for optional period-scoped totals."""
    today = timezone.now().date()
    start_date = subscription.start_date or today
    end_date = (
        subscription.end_date
        if subscription.end_date and subscription.end_date < today
        else today
    )
    if end_date < start_date:
        end_date = start_date
    return start_date, end_date


def _serialize_plan(plan) -> dict:
    if not plan:
        return {}
    return {
        "id": plan.id,
        "name": plan.name,
        "tier": plan.tier,
        "description": plan.description,
        "price": float(plan.price),
        "discount_percentage": float(plan.discount_percentage or 0),
        "user_limit": plan.user_limit,
        "api_calls_per_month": plan.api_calls_per_month,
        "minutes_per_month": plan.minutes_per_month,
        "ai_tokens_per_month": plan.ai_tokens_per_month,
        "embeddings_per_month": plan.embeddings_per_month,
        "ai_agents_count": plan.ai_agents_count,
        "is_active": plan.is_active,
        "is_popular": plan.is_popular,
        "tax_rate": float(plan.tax_rate or 0),
    }


def _serialize_subscription(subscription: ClientSubscription) -> dict:
    sub_type = subscription.subscription_type
    return {
        "id": subscription.id,
        "billing_cycle": subscription.billing_cycle,
        "status": subscription.status,
        "payment_status": subscription.payment_status,
        "start_date": subscription.start_date.isoformat() if subscription.start_date else None,
        "end_date": subscription.end_date.isoformat() if subscription.end_date else None,
        "trial_end_date": (
            subscription.trial_end_date.isoformat() if subscription.trial_end_date else None
        ),
        "cancelled_at": (
            subscription.cancelled_at.isoformat() if subscription.cancelled_at else None
        ),
        "next_billing_date": (
            subscription.next_billing_date.isoformat() if subscription.next_billing_date else None
        ),
        "amount": float(subscription.amount) if subscription.amount is not None else None,
        "currency": subscription.currency,
        "auto_renew": subscription.auto_renew,
        "cancellation_reason": subscription.cancellation_reason,
        "minutes_used": float(subscription.minutes_used or 0),
        "ai_tokens_used": int(subscription.ai_tokens_used or 0),
        "embeddings_used": int(subscription.embeddings_used or 0),
        "usage_period_start": (
            subscription.usage_period_start.isoformat()
            if subscription.usage_period_start
            else None
        ),
        "emergency_grace_ends_at": (
            subscription.emergency_grace_ends_at.isoformat()
            if subscription.emergency_grace_ends_at
            else None
        ),
        "created_at": subscription.created_at.isoformat() if subscription.created_at else None,
        "updated_at": subscription.updated_at.isoformat() if subscription.updated_at else None,
        "subscription_type": {
            "id": sub_type.id,
            "name": sub_type.name,
        }
        if sub_type
        else None,
        "days_remaining": subscription.days_remaining(),
        "is_active": subscription.is_active(),
        "grace_active": subscription.grace_is_active(),
    }


def _build_usage_block(
    client: Client,
    plan,
    subscription: ClientSubscription | None,
    *,
    period_start=None,
    period_end=None,
) -> dict:
    users_count = CustomUser.objects.filter(client=client).count() if client else 0
    user_limit = plan.user_limit if plan else 0

    counter_minutes = float(subscription.minutes_used or 0) if subscription else 0.0
    counter_tokens = int(subscription.ai_tokens_used or 0) if subscription else 0
    counter_embeddings = int(subscription.embeddings_used or 0) if subscription else 0

    minutes_limit = int(plan.minutes_per_month or 0) if plan else 0
    tokens_limit = int(plan.ai_tokens_per_month or 0) if plan else 0
    embeddings_limit = int(plan.embeddings_per_month or 0) if plan else 0

    return {
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "minutes": {
            "used": counter_minutes,
            "logged": 0,
            "limit": minutes_limit,
            "remaining": max(0, round(minutes_limit - counter_minutes, 4)),
            "call_count": 0,
            "total_seconds": 0,
            "source": "subscription",
            "info": "",
        },
        "tokens": {
            "embedding_tokens": 0,
            "response_tokens": 0,
            "request_tokens": 0,
            "total_tokens": counter_tokens,
            "logged_total_tokens": 0,
            "limit": tokens_limit,
            "remaining": max(0, tokens_limit - counter_tokens),
            "chat_requests": 0,
            "source": "subscription",
            "info": "",
        },
        "embeddings": {
            "used": counter_embeddings,
            "logged_total": 0,
            "upload_embeddings": 0,
            "query_embeddings": 0,
            "upload_count": 0,
            "limit": embeddings_limit,
            "remaining": max(0, embeddings_limit - counter_embeddings),
            "source_upload": "",
            "source_query": "",
            "info": "",
        },
        "users_count": users_count,
        "user_limit": user_limit,
        "agents_count": 0,
        "agents_limit": 0,
        "enable_chatbot": False,
        "enable_ai_agent": False,
        "subscription_counters": {
            "minutes_used": counter_minutes,
            "ai_tokens_used": counter_tokens,
            "embeddings_used": counter_embeddings,
        },
    }


def build_client_subscription_overview(client: Client, *, user=None) -> dict:
    subscription = get_client_subscription(client) if client else None
    access = build_access_status(client, user=user) if client else {}

    if not subscription or not subscription.plan:
        usage = _build_usage_block(
            client,
            None,
            subscription,
            period_start=None,
            period_end=timezone.now().date() if client else None,
        )
        return {
            "access": access,
            "subscription": None,
            "plan": {},
            "usage": usage,
            "usage_lifetime": usage,
        }

    subscription = (
        ClientSubscription.objects.select_related("plan", "subscription_type")
        .get(pk=subscription.pk)
    )
    plan = subscription.plan

    period_start, period_end = _billing_period_bounds(subscription)
    billing_usage = _build_usage_block(
        client,
        plan,
        subscription,
        period_start=period_start,
        period_end=period_end,
    )
    lifetime_usage = _build_usage_block(
        client,
        plan,
        subscription,
        period_start=subscription.start_date,
        period_end=timezone.now().date(),
    )

    return {
        "access": access,
        "subscription": _serialize_subscription(subscription),
        "plan": _serialize_plan(plan),
        "usage": billing_usage,
        "usage_lifetime": lifetime_usage,
        "usage_billing_period": billing_usage,
    }
