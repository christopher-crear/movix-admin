from django.core.cache import cache
from django.db import DatabaseError

from .models import AuditLog, ContactRequest, DriverInboxMessage, DriverMonthlyPayment, Profile, SystemSetting


def panel_context(request):
    context = {
        "top_activity": [],
        "new_contact_count": 0,
        "pending_payment_count": 0,
        "pending_profile_count": 0,
        "admin_alert_count": 0,
        "driver_unread_count": 0,
        "is_driver_portal": bool(request.session.get("portal_profile_id"))
        and not (request.user.is_authenticated and request.user.is_staff),
        "system_config": {},
    }
    if context["is_driver_portal"]:
        try:
            context["driver_unread_count"] = DriverInboxMessage.objects.filter(
                driver_id=request.session.get("portal_profile_id"), is_read=False
            ).count()
        except (DatabaseError, ValueError):
            pass
        try:
            setting = SystemSetting.objects.filter(pk="general").first()
            context["system_config"] = setting.value if setting and isinstance(setting.value, dict) else {}
            if context["system_config"]:
                cache.set("movix-system-settings", context["system_config"], None)
        except DatabaseError:
            pass
        return context
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

        payment_count = cache.get("movix-pending-payment-count")
        if payment_count is None:
            payment_count = DriverMonthlyPayment.objects.filter(status=DriverMonthlyPayment.STATUS_PENDING).count()
            cache.set("movix-pending-payment-count", payment_count, 30)
        context["pending_payment_count"] = payment_count
        profile_count = Profile.objects.filter(verification_status="pending").count()
        context["pending_profile_count"] = profile_count
        context["admin_alert_count"] = payment_count + profile_count
        setting = SystemSetting.objects.filter(pk="general").first()
        context["system_config"] = setting.value if setting and isinstance(setting.value, dict) else {}
        if context["system_config"]:
            cache.set("movix-system-settings", context["system_config"], None)
    except DatabaseError:
        pass
    return context
