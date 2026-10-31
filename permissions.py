from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def roles_required(*allowed_roles):
    """Protect a view by role. Usage: @roles_required('admin', 'staff')."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(view):
    return roles_required("admin")(view)


def staff_or_admin_required(view):
    return roles_required("admin", "staff")(view)


def customer_required(view):
    return roles_required("customer")(view)
