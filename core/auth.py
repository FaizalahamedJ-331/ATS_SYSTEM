"""
Role-based access control helpers.

The system has two roles:

* **Admin** - a Django superuser. Full access to everything, including user
  management (promote / demote / deactivate accounts).
* **Recruiter** - any signed-up account. Full recruiting workflow (jobs,
  candidates, pipeline, screening, interviews) but no user management.

New accounts are always created as Recruiters; the seeded `admin` account is
 the superuser. Admins manage roles from the \"Users\" page.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def is_admin(user):
    """True when the user holds the Admin role (a Django superuser)."""
    return bool(user and user.is_authenticated and user.is_superuser)


def admin_required(view_func):
    """Decorator: require login *and* the Admin role, else render 403."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not is_admin(request.user):
            return render(request, "403.html", status=403)
        return view_func(request, *args, **kwargs)

    return _wrapped
