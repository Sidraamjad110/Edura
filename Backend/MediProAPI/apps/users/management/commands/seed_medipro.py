from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from MediProAPI.apps.modules.catalog import ADMIN_MODULES, CLIENT_MODULES
from MediProAPI.apps.modules.models import Module, UserModule
from MediProAPI.apps.subscription.models import SubscriptionType
from MediProAPI.apps.subscription.services.plan_modules import assign_client_sidebar_modules
from MediProAPI.apps.users.models import Language
from MediProAPI.apps.users.models import Client


User = get_user_model()


class Command(BaseCommand):
    help = "Seed MediPro languages, subscription types, and sidebar modules."

    def handle(self, *args, **options):
        language, _ = Language.objects.get_or_create(
            code="en",
            defaults={"name": "English", "is_active": True},
        )

        for name in ("Monthly", "Yearly"):
            SubscriptionType.objects.get_or_create(name=name)

        all_defs = {item["code"]: item for item in (*ADMIN_MODULES, *CLIENT_MODULES)}
        modules_by_code = {}
        for item in all_defs.values():
            module, _ = Module.objects.update_or_create(
                code=item["code"],
                defaults={
                    "description": item["description"],
                    "url": item["url"],
                    "icon": item["icon"],
                    "is_active": True,
                },
            )
            modules_by_code[item["code"]] = module

        assigned = 0
        for user in User.objects.filter(is_superuser=True, is_active=True):
            for item in ADMIN_MODULES:
                module = modules_by_code[item["code"]]
                UserModule.objects.update_or_create(
                    user=user,
                    module=module,
                    defaults={
                        "is_active": True,
                        "is_default": item["is_default"],
                        "sequence": item["sequence"],
                        "parent_id": None,
                        "show_in_sidebar": True,
                    },
                )
                assigned += 1

        for client in Client.objects.select_related("auth_user"):
            if client.auth_user_id:
                assign_client_sidebar_modules(client.auth_user)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded English language, subscription types, {len(modules_by_code)} modules, "
            f"and {assigned} admin module assignments."
        ))
        self.stdout.write(f"Default language id={language.id}")
