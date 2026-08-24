import json

from django.core.management.base import BaseCommand
from django.urls import URLPattern, URLResolver, get_resolver


def _methods(callback):
    actions = getattr(callback, "actions", None)
    if actions:
        return sorted(method.upper() for method in actions)
    view_class = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
    if not view_class:
        return []
    return [
        method.upper()
        for method in getattr(view_class, "http_method_names", [])
        if method not in {"options", "head", "trace"}
        and hasattr(view_class, method)
    ]


def iter_patterns(patterns, prefix=""):
    for pattern in patterns:
        route = f"{prefix}{pattern.pattern}"
        if isinstance(pattern, URLResolver):
            yield from iter_patterns(pattern.url_patterns, route)
            continue
        if not isinstance(pattern, URLPattern) or not route.startswith("api/"):
            continue
        callback = pattern.callback
        view_class = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
        permission_classes = getattr(view_class, "permission_classes", ()) if view_class else ()
        serializer_class = getattr(view_class, "serializer_class", None) if view_class else None
        pagination_class = getattr(view_class, "pagination_class", None) if view_class else None
        internal = route.startswith("api/celery/")
        legacy = "homeroom_" in route
        yield {
            "url": f"/{route}",
            "name": pattern.name,
            "methods": _methods(callback),
            "view": f"{callback.__module__}.{getattr(view_class, '__name__', callback.__name__)}",
            "serializer": (
                f"{serializer_class.__module__}.{serializer_class.__name__}"
                if serializer_class else None
            ),
            "permissions": [
                f"{permission.__module__}.{permission.__name__}"
                for permission in permission_classes
            ],
            "authentication": (
                "anonymous-explicit"
                if any(permission.__name__ == "AllowAny" for permission in permission_classes)
                else "configured-authentication"
            ),
            "pagination": (
                f"{pagination_class.__module__}.{pagination_class.__name__}"
                if pagination_class else None
            ),
            "frontend": not internal and not legacy,
            "classification": "internal" if internal else "legacy" if legacy else "canonical",
        }


class Command(BaseCommand):
    help = "Print the resolver-derived API route inventory as JSON."

    def handle(self, *args, **options):
        rows = sorted(iter_patterns(get_resolver().url_patterns), key=lambda row: (row["url"], row["name"] or ""))
        self.stdout.write(json.dumps(rows, indent=2))
