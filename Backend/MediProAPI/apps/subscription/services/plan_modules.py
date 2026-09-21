"""Default modules per subscription plan and auto-assignment on client subscribe."""

from django.db import transaction

from MediProAPI.apps.modules.models import Module, UserModule
from MediProAPI.apps.subscription.models import SubscriptionPlanModule


def sync_plan_modules(plan, module_ids):
    """Replace default modules for a subscription plan."""
    if module_ids is None:
        return

    unique_ids = sorted({int(mid) for mid in module_ids if mid is not None})
    valid_ids = set(
        Module.objects.filter(id__in=unique_ids, is_active=True).values_list('id', flat=True)
    )
    invalid = set(unique_ids) - valid_ids
    if invalid:
        raise ValueError(f'Invalid or inactive module IDs: {sorted(invalid)}')

    SubscriptionPlanModule.objects.filter(plan=plan).exclude(module_id__in=valid_ids).delete()

    existing = set(
        SubscriptionPlanModule.objects.filter(plan=plan).values_list('module_id', flat=True)
    )
    to_create = [
        SubscriptionPlanModule(plan=plan, module_id=mid, sequence=idx + 1)
        for idx, mid in enumerate(unique_ids)
        if mid not in existing
    ]
    if to_create:
        SubscriptionPlanModule.objects.bulk_create(to_create)

    for idx, mid in enumerate(unique_ids, start=1):
        SubscriptionPlanModule.objects.filter(plan=plan, module_id=mid).update(sequence=idx)


def get_plan_module_ids(plan_id):
    return list(
        SubscriptionPlanModule.objects.filter(plan_id=plan_id)
        .order_by('sequence', 'module_id')
        .values_list('module_id', flat=True)
    )


@transaction.atomic
def assign_plan_modules_to_client(client, plan):
    """
    Assign plan default modules to the client's auth user via user_modules.
    Skips modules already assigned; does not remove existing assignments.
    """
    if not client or not plan:
        return {'assigned': 0, 'skipped': 0}

    auth_user = getattr(client, 'auth_user', None)
    if not auth_user:
        return {'assigned': 0, 'skipped': 0, 'error': 'Client has no auth user'}

    assigned = 0
    skipped = 0
    module_rows = SubscriptionPlanModule.objects.filter(plan=plan).order_by('sequence', 'module_id')
    already_assigned = set(
        UserModule.objects.filter(user=auth_user).values_list('module_id', flat=True)
    )

    for row in module_rows:
        if row.module_id in already_assigned:
            skipped += 1
            continue
        UserModule.objects.create(
            user=auth_user,
            module_id=row.module_id,
            parent_id=row.parent_id,
            sequence=row.sequence,
            is_active=True,
            is_default=False,
            show_in_sidebar=True,
        )
        already_assigned.add(row.module_id)
        assigned += 1

    assign_client_sidebar_modules(auth_user)
    return {'assigned': assigned, 'skipped': skipped}


def assign_client_sidebar_modules(auth_user):
    """Ensure a client always has Users, My Subscription, and Module Assignment."""
    from MediProAPI.apps.modules.catalog import CLIENT_MODULES

    if not auth_user:
        return

    for item in CLIENT_MODULES:
        module = Module.objects.filter(code=item["code"], is_active=True).first()
        if not module:
            continue
        UserModule.objects.update_or_create(
            user=auth_user,
            module=module,
            defaults={
                "is_active": True,
                "is_default": item["is_default"],
                "sequence": item["sequence"],
                "parent_id": None,
                "show_in_sidebar": True,
            },
        )
