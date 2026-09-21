"""Canonical MediPro modules shown in the product."""

ADMIN_MODULES = (
    {
        "code": "medipro.users",
        "description": "Users",
        "url": "/admin/users",
        "icon": "users",
        "sequence": 1,
        "is_default": True,
    },
    {
        "code": "medipro.clients",
        "description": "Clients",
        "url": "/admin/clients",
        "icon": "building",
        "sequence": 2,
        "is_default": False,
    },
    {
        "code": "medipro.subscription",
        "description": "Subscriptions",
        "url": "/admin/subscription",
        "icon": "credit-card",
        "sequence": 3,
        "is_default": False,
    },
    {
        "code": "medipro.moduleAssignment",
        "description": "Module Assignment",
        "url": "/moduleAssignment",
        "icon": "layer-group",
        "sequence": 4,
        "is_default": False,
    },
)

CLIENT_MODULES = (
    {
        "code": "medipro.users",
        "description": "Users",
        "url": "/admin/users",
        "icon": "users",
        "sequence": 1,
        "is_default": True,
    },
    {
        "code": "medipro.mySubscription",
        "description": "My Subscription",
        "url": "/admin/my-subscription",
        "icon": "credit-card",
        "sequence": 2,
        "is_default": False,
    },
    {
        "code": "medipro.moduleAssignment",
        "description": "Module Assignment",
        "url": "/moduleAssignment",
        "icon": "layer-group",
        "sequence": 3,
        "is_default": False,
    },
)

ALLOWED_MODULE_CODES = {
    "medipro.users",
    "medipro.clients",
    "medipro.subscription",
    "medipro.moduleAssignment",
    "medipro.mySubscription",
}

ALLOWED_MODULE_URLS = {
    "/admin/users",
    "/admin/clients",
    "/admin/subscription",
    "/moduleAssignment",
    "/admin/my-subscription",
}


def _normalize_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/") or ""


def is_allowed_module(code: str | None, url: str | None = None) -> bool:
    if (code or "").strip() in ALLOWED_MODULE_CODES:
        return True
    return _normalize_url(url) in ALLOWED_MODULE_URLS


def filter_module_tree(nodes: list) -> list:
    """Keep only Users / Clients / Subscriptions / Module Assignment.

    Disallowed parents are dropped; allowed children are promoted.
    """
    kept = []
    for node in nodes or []:
        children = filter_module_tree(node.get("children") or [])
        allowed = is_allowed_module(node.get("code"), node.get("url"))
        if allowed:
            item = dict(node)
            item["children"] = children
            kept.append(item)
        else:
            kept.extend(children)
    return kept
