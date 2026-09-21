"""Subscription access checks, usage deduction, and emergency grace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from EduraAPI.apps.subscription.models import ClientSubscription
from EduraAPI.apps.users.models import Client, CustomUser

GRACE_HOURS = 24
PAID_STATUS = "Paid"


def _subscription_paid(subscription: ClientSubscription) -> bool:
    return (subscription.payment_status or "").strip() == PAID_STATUS


@dataclass
class AccessResult:
    allowed: bool
    reason: str
    message: str
    grace_active: bool = False
    grace_ends_at: Optional[str] = None
    code: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "message": self.message,
            "grace_active": self.grace_active,
            "grace_ends_at": self.grace_ends_at,
            "code": self.code,
        }


def resolve_client_for_user(user) -> Optional[Client]:
    if not user or not user.is_authenticated:
        return None
    if hasattr(user, "client_profile"):
        return user.client_profile
    if hasattr(user, "custom_profile"):
        return user.custom_profile.client
    return None


def get_client_subscription(client: Client) -> Optional[ClientSubscription]:
    if not client:
        return None
    active = (
        client.subscriptions.filter(status__in=["Active", "Trial"])
        .select_related("plan")
        .order_by("-created_at")
        .first()
    )
    if active:
        return active
    return (
        client.subscriptions.select_related("plan")
        .order_by("-created_at")
        .first()
    )


def _subscription_in_date_window(subscription: ClientSubscription) -> bool:
    now = timezone.now().date()
    return subscription.start_date <= now <= subscription.end_date


def _maybe_roll_usage_period(subscription: ClientSubscription) -> None:
    if not subscription.usage_period_start:
        subscription.usage_period_start = subscription.start_date
        subscription.save(update_fields=["usage_period_start"])
        return

    period_days = 365 if subscription.billing_cycle == "Yearly" else 30
    period_end = subscription.usage_period_start + timedelta(days=period_days)
    if timezone.now().date() >= period_end:
        subscription.minutes_used = 0
        subscription.ai_tokens_used = 0
        subscription.embeddings_used = 0
        subscription.usage_period_start = timezone.now().date()
        subscription.save(
            update_fields=[
                "minutes_used",
                "ai_tokens_used",
                "embeddings_used",
                "usage_period_start",
            ]
        )


def _grace_ends_at_iso(subscription: ClientSubscription) -> Optional[str]:
    if subscription.emergency_grace_ends_at:
        return subscription.emergency_grace_ends_at.isoformat()
    return None


def check_ai_access(client: Client, *, user=None, for_voice: bool = False) -> AccessResult:
    if user and getattr(user, "is_superuser", False):
        return AccessResult(
            allowed=True,
            reason="superuser",
            message="",
            code="SUPERUSER_BYPASS",
        )

    subscription = get_client_subscription(client)
    if not subscription or not subscription.plan:
        return AccessResult(
            allowed=False,
            reason="no_subscription",
            message="No subscription found. Please contact support to activate a plan.",
            code="NO_SUBSCRIPTION",
        )

    if not _subscription_paid(subscription):
        return AccessResult(
            allowed=False,
            reason="payment_pending",
            message=(
                "Your subscription payment is pending. Subscription features will be enabled "
                "once payment status is marked as Paid."
            ),
            code="PAYMENT_PENDING",
        )

    _maybe_roll_usage_period(subscription)
    grace_active = subscription.grace_is_active()
    grace_ends = _grace_ends_at_iso(subscription) if grace_active else None

    sub_valid = (
        subscription.status in ("Active", "Trial")
        and _subscription_in_date_window(subscription)
    )

    if not sub_valid and not grace_active:
        return AccessResult(
            allowed=False,
            reason="expired",
            message=(
                "Your subscription has expired. Renew your subscription to use "
                "subscription features."
            ),
            grace_active=False,
            code="SUBSCRIPTION_EXPIRED",
        )

    reason = "grace" if grace_active and not sub_valid else "active"
    message = ""
    if grace_active and not sub_valid:
        ends = subscription.emergency_grace_ends_at.strftime("%Y-%m-%d %H:%M") if subscription.emergency_grace_ends_at else ""
        message = (
            f"Emergency access is enabled until {ends}. Please renew your subscription."
        )

    return AccessResult(
        allowed=True,
        reason=reason,
        message=message,
        grace_active=grace_active,
        grace_ends_at=grace_ends,
        code="ACCESS_GRANTED",
    )


def _base_subscription_access(
    client: Client,
    *,
    user=None,
) -> tuple[AccessResult, ClientSubscription | None]:
    """Shared subscription/payment/expiry checks without usage limits."""
    if user and getattr(user, "is_superuser", False):
        return (
            AccessResult(allowed=True, reason="superuser", message="", code="SUPERUSER_BYPASS"),
            get_client_subscription(client),
        )

    subscription = get_client_subscription(client)
    if not subscription or not subscription.plan:
        return (
            AccessResult(
                allowed=False,
                reason="no_subscription",
                message="No subscription found. Please contact support to activate a plan.",
                code="NO_SUBSCRIPTION",
            ),
            subscription,
        )

    if not _subscription_paid(subscription):
        return (
            AccessResult(
                allowed=False,
                reason="payment_pending",
                message=(
                    "Your subscription payment is pending. Subscription features will be enabled "
                    "once payment status is marked as Paid."
                ),
                code="PAYMENT_PENDING",
            ),
            subscription,
        )

    _maybe_roll_usage_period(subscription)
    grace_active = subscription.grace_is_active()
    grace_ends = _grace_ends_at_iso(subscription) if grace_active else None

    sub_valid = (
        subscription.status in ("Active", "Trial")
        and _subscription_in_date_window(subscription)
    )

    if not sub_valid and not grace_active:
        return (
            AccessResult(
                allowed=False,
                reason="expired",
                message=(
                    "Your subscription has expired. Renew your subscription to use "
                    "subscription features."
                ),
                grace_active=False,
                code="SUBSCRIPTION_EXPIRED",
            ),
            subscription,
        )

    reason = "grace" if grace_active and not sub_valid else "active"
    message = ""
    if grace_active and not sub_valid:
        ends = (
            subscription.emergency_grace_ends_at.strftime("%Y-%m-%d %H:%M")
            if subscription.emergency_grace_ends_at
            else ""
        )
        message = (
            f"Emergency access is enabled until {ends}. Please renew your subscription."
        )

    return (
        AccessResult(
            allowed=True,
            reason=reason,
            message=message,
            grace_active=grace_active,
            grace_ends_at=grace_ends,
            code="ACCESS_GRANTED",
        ),
        subscription,
    )


def sync_embeddings_used(client: Client, subscription: ClientSubscription | None = None) -> int:
    """Return the subscription embeddings counter without deleted upload-log tables."""
    subscription = subscription or get_client_subscription(client)
    if not subscription:
        return 0
    return int(subscription.embeddings_used or 0)


def get_embeddings_remaining(client: Client) -> int:
    subscription = get_client_subscription(client)
    if not subscription or not subscription.plan:
        return 0
    used = sync_embeddings_used(client, subscription)
    limit = int(subscription.plan.embeddings_per_month or 0)
    return max(0, limit - used)


def check_upload_access(client: Client, *, user=None, required_embeddings: int = 0) -> AccessResult:
    base, _subscription = _base_subscription_access(client, user=user)
    if not base.allowed:
        return base
    return AccessResult(
        allowed=True,
        reason=base.reason,
        message=base.message,
        grace_active=base.grace_active,
        grace_ends_at=base.grace_ends_at,
        code="UPLOAD_GRANTED",
    )


def check_can_create_user(client: Client, *, user=None) -> AccessResult:
    if user and getattr(user, "is_superuser", False):
        return AccessResult(allowed=True, reason="superuser", message="", code="SUPERUSER_BYPASS")

    subscription = get_client_subscription(client)
    if not subscription or not subscription.plan:
        return AccessResult(
            allowed=False,
            reason="no_subscription",
            message="No active subscription. Cannot create users.",
            code="NO_SUBSCRIPTION",
        )

    count = CustomUser.objects.filter(client=client).count()
    limit = subscription.plan.user_limit
    if count >= limit:
        return AccessResult(
            allowed=False,
            reason="user_limit",
            message="You have reached the maximum number of users for your plan.",
            code="USER_LIMIT_REACHED",
        )
    return AccessResult(allowed=True, reason="ok", message="", code="OK")


def deduct_minutes(client: Client, duration_seconds: float) -> None:
    if duration_seconds <= 0:
        return
    minutes = Decimal(str(duration_seconds)) / Decimal("60")
    subscription = get_client_subscription(client)
    if not subscription:
        return
    with transaction.atomic():
        sub = ClientSubscription.objects.select_for_update().get(pk=subscription.pk)
        sub.minutes_used = (sub.minutes_used or 0) + minutes
        sub.save(update_fields=["minutes_used", "updated_at"])


def deduct_tokens(client: Client, token_count: int) -> None:
    if token_count <= 0:
        return
    subscription = get_client_subscription(client)
    if not subscription:
        return
    with transaction.atomic():
        sub = ClientSubscription.objects.select_for_update().get(pk=subscription.pk)
        sub.ai_tokens_used = (sub.ai_tokens_used or 0) + int(token_count)
        sub.save(update_fields=["ai_tokens_used", "updated_at"])


def deduct_embeddings(client: Client, embedding_count: int) -> None:
    if embedding_count <= 0:
        return
    subscription = get_client_subscription(client)
    if not subscription:
        return
    with transaction.atomic():
        sub = ClientSubscription.objects.select_for_update().get(pk=subscription.pk)
        sub.embeddings_used = (sub.embeddings_used or 0) + int(embedding_count)
        sub.save(update_fields=["embeddings_used", "updated_at"])


def activate_emergency_grace(client: Client, user) -> AccessResult:
    if not hasattr(user, "client_profile"):
        return AccessResult(
            allowed=False,
            reason="forbidden",
            message="Only the main client account can activate emergency access.",
            code="GRACE_FORBIDDEN",
        )

    if user.client_profile.id != client.id:
        return AccessResult(
            allowed=False,
            reason="forbidden",
            message="You can only activate emergency access for your own account.",
            code="GRACE_FORBIDDEN",
        )

    subscription = get_client_subscription(client)
    if not subscription:
        return AccessResult(
            allowed=False,
            reason="no_subscription",
            message="No subscription found for this client.",
            code="NO_SUBSCRIPTION",
        )

    if not _subscription_paid(subscription):
        return AccessResult(
            allowed=False,
            reason="payment_pending",
            message=(
                "Emergency access is unavailable while subscription payment is pending. "
                "Please complete payment first."
            ),
            code="PAYMENT_PENDING",
        )

    sub_valid = (
        subscription.status in ("Active", "Trial")
        and _subscription_in_date_window(subscription)
    )
    if sub_valid:
        return AccessResult(
            allowed=False,
            reason="already_active",
            message="Your subscription is already active. Emergency access is not needed.",
            code="SUBSCRIPTION_ACTIVE",
        )

    ends_at = timezone.now() + timedelta(hours=GRACE_HOURS)
    subscription.emergency_grace_ends_at = ends_at
    subscription.save(update_fields=["emergency_grace_ends_at", "updated_at"])

    return AccessResult(
        allowed=True,
        reason="grace",
        message=(
            f"Emergency access enabled for 24 hours (until "
            f"{ends_at.strftime('%Y-%m-%d %H:%M')}). Please renew your subscription."
        ),
        grace_active=True,
        grace_ends_at=ends_at.isoformat(),
        code="GRACE_ACTIVATED",
    )


def reset_usage_on_activation(subscription: ClientSubscription) -> None:
    subscription.reset_usage_period()
    subscription.save(
        update_fields=[
            "minutes_used",
            "ai_tokens_used",
            "embeddings_used",
            "usage_period_start",
            "emergency_grace_ends_at",
            "updated_at",
        ]
    )
