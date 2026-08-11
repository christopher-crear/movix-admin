from django.contrib import admin
from django.urls import include, path

from panel import views as panel_views


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("login/", panel_views.access_login, name="login"),
    path("logout/", panel_views.access_logout, name="logout"),
    path("", include("panel.urls")),
]
