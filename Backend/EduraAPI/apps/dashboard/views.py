from datetime import timedelta

from django.db.models import Case, IntegerField, When
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from EduraAPI.apps.modules.models import UserModule
from EduraAPI.apps.subscription.models import ClientSubscription
from EduraAPI.apps.users.models import Client, CustomUser


def _period_start(period):
    now = timezone.now()
    mapping = {
        "today": timedelta(days=1),
        "week": timedelta(days=7),
        "month": timedelta(days=30),
        "quarter": timedelta(days=90),
        "year": timedelta(days=365),
    }
    delta = mapping.get(period)
    return now - delta if delta else None


def _resolve_request_context(user):
    if hasattr(user, "client_profile"):
        return {
            "role": "client",
            "client_id": user.client_profile.id,
            "user_id": user.id,
        }

    if hasattr(user, "custom_profile"):
        return {
            "role": "custom_user",
            "client_id": user.custom_profile.client_id,
            "user_id": user.id,
        }

    if user.is_staff or user.is_superuser:
        return {"role": "admin", "client_id": None, "user_id": user.id}

    return {"role": "unknown", "client_id": None, "user_id": user.id}


def _client_label(client):
    if client.company_name:
        return client.company_name
    if client.auth_user:
        name = client.auth_user.get_full_name()
        if name:
            return name
        return client.auth_user.username
    return f"Client #{client.id}"


class DashboardOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.query_params.get("period", "month")
        since = _period_start(period)
        ctx = _resolve_request_context(request.user)
        is_admin = ctx["role"] == "admin"
        client_id = ctx["client_id"]

        clients_qs = Client.objects.all()
        users_qs = CustomUser.objects.all()
        subscriptions_qs = ClientSubscription.objects.all()

        if not is_admin and client_id:
            clients_qs = clients_qs.filter(id=client_id)
            users_qs = users_qs.filter(client_id=client_id)
            subscriptions_qs = subscriptions_qs.filter(client_id=client_id)

        summary = {
            "clients": clients_qs.count() if is_admin else 1,
            "users": users_qs.filter(is_active=True).count(),
            "active_subscriptions": subscriptions_qs.filter(
                status__in=["Active", "Trial"]
            ).count(),
        }

        response = {
            "success": True,
            "role": ctx["role"],
            "period": period,
            "summary": summary,
            "charts": {
                "activity_trend": {"labels": []},
                "module_usage": {"labels": [], "values": []},
            },
            "recent_activity": self._recent_activity(users_qs, clients_qs, since),
            "quick_links": self._quick_links(request.user),
        }

        if is_admin:
            response["recent_clients"] = self._recent_clients()

        return Response(response)

    def _recent_clients(self):
        clients = (
            Client.objects.select_related("auth_user")
            .order_by("-created_at")[:6]
        )
        return [
            {
                "id": client.id,
                "name": _client_label(client),
                "email": client.auth_user.email if client.auth_user else "",
                "is_active": client.is_active,
                "created_at": client.created_at,
            }
            for client in clients
        ]

    def _recent_activity(self, users_qs, clients_qs, since):
        activities = []

        recent_users = users_qs.select_related("auth_user")
        recent_clients = clients_qs.select_related("auth_user")
        if since:
            recent_users = recent_users.filter(created_at__gte=since)
            recent_clients = recent_clients.filter(created_at__gte=since)

        for custom_user in recent_users.order_by("-created_at")[:8]:
            username = (
                custom_user.auth_user.username
                if custom_user.auth_user
                else "User"
            )
            activities.append(
                {
                    "type": "user",
                    "title": username,
                    "subtitle": "User created",
                    "timestamp": custom_user.created_at,
                }
            )

        for client in recent_clients.order_by("-created_at")[:8]:
            activities.append(
                {
                    "type": "client",
                    "title": _client_label(client),
                    "subtitle": "Client created",
                    "timestamp": client.created_at,
                }
            )

        activities.sort(key=lambda item: item["timestamp"] or timezone.now(), reverse=True)
        return activities[:10]

    def _normalize_module_url(self, url):
        if not url:
            return None
        url = str(url).strip()
        if not url:
            return None
        return url if url.startswith("/") else f"/{url}"

    def _quick_links(self, user):
        """Return up to 6 quick-access links from modules assigned to this user."""
        dashboard_codes = {"medipro.dashboard", "dashboard"}
        assigned = (
            UserModule.objects.select_related("module")
            .filter(
                user_id=user.id,
                is_active=True,
                module__is_active=True,
            )
            .exclude(module__code__in=dashboard_codes)
            .annotate(
                order_priority=Case(
                    When(is_default=True, then=0),
                    default=1,
                    output_field=IntegerField(),
                )
            )
            .order_by("order_priority", "sequence", "module__code")
        )

        links = []
        for user_module in assigned:
            module = user_module.module
            url = self._normalize_module_url(module.url)
            if not url:
                continue
            links.append(
                {
                    "title": module.description or module.code,
                    "to": url,
                    "icon": module.icon or "circle",
                    "code": module.code,
                    "sequence": user_module.sequence or 9999,
                }
            )
            if len(links) >= 6:
                break
        return links
