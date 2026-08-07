from django.contrib import admin

from .models import AdminProfile, ContactRequest


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "city", "updated_at")
    search_fields = ("user__username", "user__email", "phone", "city")


@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "request_type", "status", "created_at")
    list_filter = ("status", "request_type", "created_at")
    search_fields = ("full_name", "email", "phone", "subject", "message")
    readonly_fields = ("ip_address", "user_agent", "created_at", "updated_at")
