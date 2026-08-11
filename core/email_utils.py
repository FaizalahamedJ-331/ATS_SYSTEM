"""Signed-token email verification helpers.

The verification token is a signed, time-stamped payload (user pk) so it
needs no database storage. It expires after EMAIL_VERIFY_TIMEOUT_HOURS.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

EMAIL_VERIFY_TIMEOUT_HOURS = 48
VERIFY_SALT = "talentpulse-email-verify"


def _signer():
    return TimestampSigner(key=settings.SECRET_KEY, salt=VERIFY_SALT)


def make_verification_token(user_pk):
    return _signer().sign(str(user_pk))


def parse_verification_token(token, max_age=timedelta(hours=EMAIL_VERIFY_TIMEOUT_HOURS)):
    """Return the user pk from a valid token, or None when invalid/expired."""
    try:
        payload = _signer().unsign(token, max_age=max_age.total_seconds())
        return int(payload) if str(payload).isdigit() else None
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None


def token_expiry_display():
    """Human text like '2 days' for templates (48 hours)."""
    return "2 days"


def _absolute_link(path, request=None):
    """Turn a relative URL path into a clickable link for an email.

    Uses the request's host when one is available (web-sent mail), otherwise
    the configured SITE_URL (cron / management-command mail). Falls back to
    the relative path when neither exists — the console backend in dev
    prints it either way.
    """
    if request:
        return request.build_absolute_uri(path)
    if getattr(settings, "SITE_URL", ""):
        return f"{settings.SITE_URL}{path}"
    return path


def _send_email(user, subject, template_prefix, context, request=None):
    """Shared mechanics for any user-facing email: render the HTML + text
    templates and send. Returns True when sent and never raises — mail
    delivery must not break the caller (a signup flow, a cron run, or a
    password reset).
    """
    text = render_to_string(f"emails/{template_prefix}.txt", context)
    html = render_to_string(f"emails/{template_prefix}.html", context)
    try:
        send_mail(
            subject,
            text,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html,
            fail_silently=False,
        )
    except Exception:
        # e.g. no SMTP configured, or the console backend hit a non-encodable
        # character. The caller handles the False gracefully.
        return False
    return True


def _verification_context(user, link, request=None):
    return {
        "user": user,
        "verify_link": link,
        "expiry": token_expiry_display(),
    }


def _send_verification_email(user, subject, template_prefix, request=None):
    """Shared mechanics for verification emails: build a fresh signed link,
    render the HTML + text templates, and send. Returns True when sent.
    """
    token = make_verification_token(user.pk)
    link = _absolute_link(reverse("verify_email", args=[token]), request)
    return _send_email(
        user,
        subject,
        template_prefix,
        _verification_context(user, link, request),
        request=request,
    )


def send_verification_email(user, request=None):
    """Send the welcome + verification email. Returns True when sent.

    The verify link is built from the request when available so it works
    behind any host; falls back to SITE_URL for request-less sends.
    """
    return _send_verification_email(
        user,
        "Welcome to TalentPulse — please verify your email",
        "verify_email",
        request=request,
    )


def send_verification_reminder(user, request=None):
    """Send the "still waiting" reminder for an account stuck unverified.

    Same mechanics as the welcome email (fresh signed link), but with a
    nudge-oriented subject and copy. Uses SITE_URL to build an absolute link
    when run from cron (no request). Returns True when sent.
    """
    return _send_verification_email(
        user,
        "Still waiting on your TalentPulse account — verify your email",
        "verify_reminder",
        request=request,
    )


def reset_token_expiry_display():
    """Human text for the reset email, derived from the actual timeout so it
    never lies when PASSWORD_RESET_TIMEOUT is overridden."""
    days = getattr(settings, "PASSWORD_RESET_TIMEOUT", 259200) // 86400
    return f"{max(days, 1)} day{'s' if days != 1 else ''}"


def send_password_reset_email(user, uid, token, request=None):
    """Send the "reset your password" email for the forgot-password flow.

    `uid` and `token` come from Django's PasswordResetForm (base64 user pk
    plus signed, time-limited token). Returns True when sent and never
    raises — the reset view must keep working if mail delivery fails.
    """
    path = reverse(
        "password_reset_confirm",
        kwargs={"uidb64": uid, "token": token},
    )
    link = _absolute_link(path, request)
    context = {
        "user": user,
        "reset_link": link,
        "expiry": reset_token_expiry_display(),
    }
    return _send_email(
        user,
        "Reset your TalentPulse password",
        "password_reset",
        context,
        request=request,
    )


def send_login_alert(user, request=None):
    """Email the user about a sign-in from an untrusted device.

    Part of the opt-in "notify me of new logins" setting: fired right after
    a successful login that had no valid trust cookie. Includes the friendly
    device label, IP and time so the user can judge whether it was them.
    Returns True when sent and never raises (mail failure must not break a
    login).
    """
    from core.trust import client_ip, device_label

    user_agent = (request.META.get("HTTP_USER_AGENT") if request else "") or ""
    context = {
        "user": user,
        "device": device_label(user_agent) or "Unknown device",
        "ip": client_ip(request) if request else "Unknown",
        "time": timezone.now(),
        "change_password_link": _absolute_link(reverse("password_change"), request),
    }
    return _send_email(
        user,
        "New sign-in to your TalentPulse account",
        "login_alert",
        context,
        request=request,
    )


def send_security_digest(user, events, request=None, period="the last day"):
    """Email a daily summary of the user's recent security-log events.

    ``events`` is a queryset of SecurityLog rows (newest first). Only the
    latest 20 are shown in the email; the rest collapse to a "+N more"
    line, and the summary mirrors the security-log page's filter groups.
    Returns True when sent and never raises - cron must keep running even
    if one user's mail fails.
    """
    from django.db.models import Count

    from core.security_log import EVENT_LABELS, FILTER_GROUPS

    shown = list(events[:20])
    group_names = {slug: label for slug, label, _codes in FILTER_GROUPS if slug != "all"}
    event_group = {}
    for slug, _label, codes in FILTER_GROUPS:
        if codes:
            for code in codes:
                event_group[code] = slug
    # Tally counts with one grouped DB query instead of fetching every row.
    counts = {slug: 0 for slug in group_names}
    for code, count in (
        events.values("event").annotate(c=Count("id")).values_list("event", "c")
    ):
        slug = event_group.get(code, "account")
        if slug in counts:
            counts[slug] += count
    context = {
        "user": user,
        "period": period,
        "events": [
            {
                "label": EVENT_LABELS.get(e.event, e.event),
                "detail": e.detail,
                "created_at": e.created_at,
                "ip": e.ip_address,
            }
            for e in shown
        ],
        "groups": [(group_names[slug], count) for slug, count in counts.items() if count],
        "more_count": max(0, events.count() - len(shown)),
        "log_link": _absolute_link(reverse("security_log"), request),
    }
    return _send_email(
        user,
        "Your daily TalentPulse security digest",
        "security_digest",
        context,
        request=request,
    )


def get_unverified_user_by_email(email):
    """Return the first unverified, active user with this email (or None).
    Used by the resend form — deliberately quiet about whether the account
    exists to avoid leaking signup status.
    """
    if not email:
        return None
    return (
        User.objects.filter(email__iexact=email.strip(), is_active=True)
        .exclude(is_superuser=True)
        .select_related("profile")
        .filter(profile__email_verified=False)
        .order_by("-date_joined")
        .first()
    )
