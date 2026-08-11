"""Per-user security audit log.

Every meaningful account-security event - 2FA changes, trusted-device
activity, recovery-code issuance, password changes and sign-ins - is
recorded on the user's profile page so they can spot anything suspicious.
Events are capped per user (oldest pruned) to bound table growth.
"""

from django.db import transaction

from core.models import SecurityLog

# Cap rows per user so the audit trail stays useful without growing forever.
MAX_EVENTS_PER_USER = 500

# Filter groups for the log page: (slug, label, event codes). "all" (None)
# shows everything; the rest group related events under one chip.
FILTER_GROUPS = [
    ("all", "All", None),
    ("signins", "Sign-ins", ["login", "2fa_login"]),
    (
        "twofa",
        "2FA & codes",
        [
            "2fa_enabled",
            "2fa_disabled",
            "recovery_codes_generated",
            "recovery_codes_regenerated",
        ],
    ),
    ("devices", "Devices", ["device_trusted", "device_revoked", "devices_revoked_all"]),
    ("account", "Account", ["password_changed", "alerts_toggled"]),
]


def filter_events(queryset, slug):
    """Narrow a security-log queryset to one filter group.

    Unknown or empty slugs return the queryset unchanged ("all"), so a
    tampered query param can never hide events.
    """
    for key, _label, events in FILTER_GROUPS:
        if key == slug:
            return queryset if events is None else queryset.filter(event__in=events)
    return queryset


# Event code -> short human label shown in the UI.
EVENT_LABELS = {
    "login": "Signed in",
    "2fa_login": "Signed in with 2FA",
    "2fa_enabled": "Two-factor authentication enabled",
    "2fa_disabled": "Two-factor authentication disabled",
    "device_trusted": "Browser trusted for 30 days",
    "device_revoked": "Trusted browser forgotten",
    "devices_revoked_all": "All trusted browsers forgotten",
    "recovery_codes_generated": "Recovery codes issued",
    "recovery_codes_regenerated": "Recovery codes regenerated",
    "password_changed": "Password changed",
    "alerts_toggled": "Sign-in alerts changed",
    "sessions_signed_out": "Other sessions signed out",
}


def log_event(user, event, request=None, detail=""):
    """Record one security event for ``user`` (never raises).

    ``detail`` is short free text (e.g. the friendly device label). Returns
    the created row, or None on error - auditing must never break the
    underlying action (a login, a 2FA toggle, an email send).
    """
    if user is None:
        return None
    ip = None
    if request is not None:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None
    try:
        with transaction.atomic():
            entry = SecurityLog.objects.create(
                user=user,
                event=event,
                detail=(detail or "")[:255],
                ip_address=ip[:45] if ip else None,
            )
            # Retention: prune only on ~every 50th event so the login hot
            # path (which logs every sign-in) skips the count query almost
            # always. The cap can briefly overshoot by up to 49 rows before
            # snapping back - a deliberate cost/accuracy trade-off.
            if entry.pk % 50 == 0:
                excess = SecurityLog.objects.filter(user=user).count() - MAX_EVENTS_PER_USER
                if excess > 0:
                    # Oldest first; pk breaks ties when several events share a
                    # timestamp (auto_now_add is second-resolution).
                    oldest = SecurityLog.objects.filter(user=user).order_by("created_at", "pk")[:excess]
                    SecurityLog.objects.filter(pk__in=[e.pk for e in oldest]).delete()
        return entry
    except Exception:
        return None
