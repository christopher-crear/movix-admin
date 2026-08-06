from django.core.cache import cache
from django.db import DatabaseError

from .models import AuditLog


def panel_context(request):
    context = {"top_activity": []}
    if not request.user.is_authenticated or not request.user.is_staff:
        return context
    cached = cache.get("movix-top-activity")
    if cached is not None:
        context["top_activity"] = cached
        return context
    try:
        context["top_activity"] = list(AuditLog.objects.all()[:5])
        cache.set("movix-top-activity", context["top_activity"], 30)
    except DatabaseError:
        pass
    return context
