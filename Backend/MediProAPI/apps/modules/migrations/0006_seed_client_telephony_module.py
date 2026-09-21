from django.db import migrations


def seed_medipro_modules(apps, schema_editor):
    Module = apps.get_model("modules", "Module")
    modules = [
        {
            "code": "medipro.users",
            "description": "Users",
            "url": "/admin/users",
            "icon": "users",
            "is_active": True,
        },
        {
            "code": "medipro.clients",
            "description": "Clients",
            "url": "/admin/clients",
            "icon": "building",
            "is_active": True,
        },
        {
            "code": "medipro.subscription",
            "description": "Subscriptions",
            "url": "/admin/subscription",
            "icon": "credit-card",
            "is_active": True,
        },
        {
            "code": "medipro.moduleAssignment",
            "description": "Module Assignment",
            "url": "/moduleAssignment",
            "icon": "layer-group",
            "is_active": True,
        },
        {
            "code": "medipro.mySubscription",
            "description": "My Subscription",
            "url": "/admin/my-subscription",
            "icon": "credit-card",
            "is_active": True,
        },
    ]
    for defaults in modules:
        Module.objects.update_or_create(code=defaults["code"], defaults=defaults)


def unseed_medipro_modules(apps, schema_editor):
    Module = apps.get_model("modules", "Module")
    Module.objects.filter(code__startswith="medipro.").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("modules", "0005_alter_usermodule_options"),
    ]

    operations = [
        migrations.RunPython(seed_medipro_modules, unseed_medipro_modules),
    ]
