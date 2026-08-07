from django.core.cache import cache
from django.db import DatabaseError

from .models import AuditLog, ContactRequest


def panel_context(request):
    context = {"top_activity": [], "new_contact_count": 0}
    if not request.user.is_authenticated or not request.user.is_staff:
        return context
    try:
        cached = cache.get("movix-top-activity")
        if cached is None:
            cached = list(AuditLog.objects.all()[:5])
            cache.set("movix-top-activity", cached, 30)
        context["top_activity"] = cached

        new_count = cache.get("movix-new-contact-count")
        if new_count is None:
            new_count = ContactRequest.objects.filter(status=ContactRequest.STATUS_NEW).count()
            cache.set("movix-new-contact-count", new_count, 30)
        context["new_contact_count"] = new_count
    except DatabaseError:
        pass
    return context
