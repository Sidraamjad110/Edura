from django.core.management.base import BaseCommand

from MediProAPI.apps.modules.models import Module
from MediProAPI.apps.users.models import Language, Localization

DASHBOARD_LOCALIZATIONS = [
    ("dashboard.page.title", "Analytics Dashboard"),
    ("dashboard.welcome.back", "Welcome back"),
    ("dashboard.button.start.tour", "Start Tour"),
    ("dashboard.role.analytics", "Analytics"),
    ("dashboard.role.admin", "Admin"),
    ("dashboard.role.client", "Client"),
    ("dashboard.subtitle.admin", "Platform-wide overview across chatbot, AI agents, calls, and clients."),
    ("dashboard.subtitle.client", "Your workspace performance at a glance."),
    ("dashboard.period.today", "Today"),
    ("dashboard.period.week", "This Week"),
    ("dashboard.period.month", "This Month"),
    ("dashboard.period.quarter", "Quarter"),
    ("dashboard.period.year", "Year"),
    ("dashboard.error.retry", "Retry"),
    ("dashboard.error.load", "Failed to load dashboard data"),
    ("dashboard.stats.chatbot.requests", "Chatbot Requests"),
    ("dashboard.stats.documents", "Documents"),
    ("dashboard.stats.live.calls", "Live Calls"),
    ("dashboard.call.overview.title", "Scheduled Calls Overview"),
    ("dashboard.call.overview.subtitle", "Live snapshot of your call queue — refreshes automatically."),
    ("dashboard.call.overview.live", "Live"),
    ("dashboard.call.overview.total", "Total Calls"),
    ("dashboard.call.overview.scheduled", "Scheduled Calls"),
    ("dashboard.call.overview.completed.remaining", "Completed / Remaining"),
    ("dashboard.call.overview.processing", "Processing"),
    ("dashboard.call.overview.blocked", "Blocked"),
    ("dashboard.call.overview.completed.label", "Done"),
    ("dashboard.call.overview.remaining.label", "Left"),
    ("dashboard.call.overview.daily.hint", "Today {done}/{limit} · {left} left today"),
    ("dashboard.chart.activity.title", "Activity Trend"),
    ("dashboard.chart.activity.subtitle", "Chatbot requests and document uploads over time"),
    ("dashboard.chart.activity.empty", "No activity data for this period."),
    ("dashboard.chart.activity.chat.requests", "Chat Requests"),
    ("dashboard.chart.activity.document.uploads", "Document Uploads"),
    ("dashboard.chart.module.title", "Module Usage"),
    ("dashboard.chart.module.subtitle", "Distribution across product areas"),
    ("dashboard.chart.module.empty", "No module usage yet."),
    ("dashboard.chart.clients.title", "Top Clients by Chat Activity"),
    ("dashboard.chart.clients.subtitle", "Most active client accounts in the selected period"),
    ("dashboard.chart.clients.empty", "No client activity yet."),
    ("dashboard.agent.availability.title", "Agent Availability"),
    ("dashboard.agent.availability.subtitle", "{count} AI agents in your workspace"),
    ("dashboard.agent.availability.online", "{percent}% online"),
    ("dashboard.agent.available", "Available"),
    ("dashboard.agent.busy", "Busy"),
    ("dashboard.agent.offline", "Offline"),
    ("dashboard.quick.access.title", "Quick Access"),
    ("dashboard.quick.access.subtitle", "Jump into key modules"),
    ("dashboard.quick.access.empty", "No assigned modules available for quick access."),
    ("dashboard.quick.chatbot.upload", "Chatbot Upload"),
    ("dashboard.quick.chatbot.analytics", "Chatbot Analytics"),
    ("dashboard.quick.live.calls", "Live Calls"),
    ("dashboard.quick.ai.agents", "AI Agents"),
    ("dashboard.quick.clients", "Clients"),
    ("dashboard.quick.campaigns", "Campaigns"),
    ("dashboard.quick.contacts", "Contacts"),
    ("dashboard.snapshot.title", "Platform Snapshot"),
    ("dashboard.snapshot.subtitle", "High-level counts across the workspace"),
    ("dashboard.snapshot.documents", "Documents"),
    ("dashboard.snapshot.live.calls", "Live Calls"),
    ("dashboard.mini.contacts", "Contacts"),
    ("dashboard.mini.uploads", "Uploads"),
    ("dashboard.mini.tokens", "Tokens Used"),
    ("dashboard.tour.header.title", "Analytics overview"),
    ("dashboard.tour.header.description", "Your role-based dashboard summarises chatbot, agents, calls, and client activity."),
    ("dashboard.tour.stats.title", "Key metrics"),
    ("dashboard.tour.stats.description", "Track the most important numbers for your account or the whole platform."),
    ("dashboard.tour.charts.title", "Visual insights"),
    ("dashboard.tour.charts.description", "Charts show trends and module usage over the selected period."),
    ("dashboard.module.chatbot", "Chatbot"),
    ("dashboard.module.ai.agents", "AI Agents"),
    ("dashboard.module.live.calls", "Live Calls"),
    ("dashboard.module.campaigns", "Campaigns"),
]


class Command(BaseCommand):
    help = "Seed dashboard localization keys into the localizations table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--language",
            default="en",
            help="Language code to seed (default: en)",
        )

    def handle(self, *args, **options):
        language_code = options["language"]
        language, _ = Language.objects.get_or_create(
            code=language_code,
            defaults={"name": language_code.upper(), "is_active": True},
        )

        module, _ = Module.objects.get_or_create(
            code="medipro.users",
            defaults={
                "description": "Users",
                "url": "/admin/users",
                "icon": "users",
                "is_active": True,
            },
        )

        created = 0
        updated = 0
        for code, text in DASHBOARD_LOCALIZATIONS:
            localization, was_created = Localization.objects.update_or_create(
                code=code,
                language=language,
                module=module,
                defaults={"text": text},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Dashboard localizations seeded for '{language_code}' "
                f"(module: {module.code}, created: {created}, updated: {updated})."
            )
        )
