from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            raise PermissionDenied("Esta sección es exclusiva para administradores.")
        return view_func(request, *args, **kwargs)

    return wrapped
