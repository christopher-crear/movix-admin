from django.contrib import admin

from .models import AdminProfile


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "city", "updated_at")
    search_fields = ("user__username", "user__email", "phone", "city")
