from django.contrib import admin
from django.urls import include, path

from panel import views as panel_views


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("login/", panel_views.access_login, name="login"),
    path("registro-transportista/", panel_views.driver_registration, name="driver_registration"),
    path("terminos-y-condiciones/", panel_views.terms_and_conditions, name="terms_and_conditions"),
    path("recuperar-contrasena/", panel_views.password_recovery, name="password_recovery"),
    path("recuperar-contrasena/<str:token>/", panel_views.password_reset_confirm, name="password_reset_confirm"),
    path("logout/", panel_views.access_logout, name="logout"),
    path("", include("panel.urls")),
]
