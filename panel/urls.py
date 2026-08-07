from django.urls import path

from . import views


app_name = "panel"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("demo/", views.demo_app, name="demo"),
    path("administracion/", views.dashboard, name="dashboard"),
    path("buscar/", views.global_search, name="search"),
    path("solicitudes/", views.contact_request_list, name="contact_request_list"),
    path("solicitudes/<uuid:request_id>/", views.contact_request_detail, name="contact_request_detail"),
    path("solicitudes/<uuid:request_id>/estado/<str:status>/", views.contact_request_status, name="contact_request_status"),
    path("personas/<str:kind>/", views.profile_list, name="profile_list"),
    path("personas/<str:kind>/nuevo/", views.profile_create, name="profile_create"),
    path("personas/<str:kind>/exportar/", views.profile_export, name="profile_export"),
    path("personas/<str:kind>/<uuid:profile_id>/", views.profile_detail, name="profile_detail"),
    path("personas/<str:kind>/<uuid:profile_id>/editar/", views.profile_edit, name="profile_edit"),
    path("personas/<str:kind>/<uuid:profile_id>/eliminar/", views.profile_delete, name="profile_delete"),
    path("personas/<str:kind>/<uuid:profile_id>/estado/", views.profile_toggle, name="profile_toggle"),
    path("verificaciones/", views.verification_list, name="verification_list"),
    path("verificaciones/<uuid:profile_id>/", views.verification_detail, name="verification_detail"),
    path("verificaciones/<uuid:profile_id>/<str:decision>/", views.verification_update, name="verification_update"),
    path("archivos/<uuid:profile_id>/<str:document_key>/<str:action>/", views.document_access, name="document_access"),
    path("notificaciones/", views.notifications_view, name="notifications"),
    path("publicidad/", views.advertisements_view, name="advertisements"),
    path("publicidad/<uuid:advertisement_id>/estado/", views.advertisement_toggle, name="advertisement_toggle"),
    path("publicidad/<uuid:advertisement_id>/eliminar/", views.advertisement_delete, name="advertisement_delete"),
    path("perfil/", views.admin_profile_view, name="admin_profile"),
    path("perfil/eliminar/", views.admin_account_delete, name="admin_account_delete"),
    path("configuracion/", views.settings_view, name="settings"),
]
