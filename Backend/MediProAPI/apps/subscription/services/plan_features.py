"""Detect which product areas a subscription plan includes."""

from __future__ import annotations

CHATBOT_MODULE_CODES = frozenset()
AI_AGENT_MODULE_CODES = frozenset()


def _normalize_code(code: str | None) -> str:
    return (code or "").strip().lower()


def get_plan_module_codes(plan) -> set[str]:
    if not plan:
        return set()
    from MediProAPI.apps.modules.models import Module
    from MediProAPI.apps.subscription.models import SubscriptionPlanModule

    module_ids = SubscriptionPlanModule.objects.filter(plan=plan).values_list(
        "module_id", flat=True
    )
    codes = Module.objects.filter(id__in=module_ids).values_list("code", flat=True)
    return {_normalize_code(c) for c in codes if c}


def plan_includes_chatbot(plan) -> bool:
    return False


def plan_includes_ai_agent(plan) -> bool:
    return False


def plan_feature_flags(plan) -> dict:
    return {
        "enable_chatbot": False,
        "enable_ai_agent": False,
    }
