""""Remember this device" trust cookies for 2FA.

When a user with TOTP 2FA enabled completes the challenge and opts in, we
hand the browser an HttpOnly cookie containing a random 256-bit token. Only
the SHA-256 digest of that token is stored (in TrustedDevice), so a database
leak never yields a usable trust cookie. On later logins, a valid unexpired
token for *that user* lets them skip the 2FA challenge on that browser.

Security notes:
- Tokens are 256 bits of entropy from ``secrets`` -- unguessable.
- The cookie is scoped to the whole site, HttpOnly (JS can't read it),
  SameSite=Lax (no cross-site sends), and Secure whenever the session
  cookie is (i.e. in production).
- Each device row is bound to one user, so a cookie from one account can
  never skip 2FA for another.
- Devices are per-row revocable from Settings, and disabling 2FA wipes them.
"""

import hashlib
import random
from datetime import timedelta
from secrets import token_hex

from django.conf import settings
from django.utils import timezone

from core.models import TrustedDevice

TRUST_COOKIE_NAME = "tp_trust"
TRUST_DAYS_DEFAULT = 30

# Don't write last_used_at on every single request-login; once per window is
# plenty for the "last used" display and keeps writes minimal.
_LAST_USED_WRITE_WINDOW = timedelta(minutes=15)


def trust_days():
    """How long a trust cookie stays valid (default 30 days)."""
    return int(getattr(settings, "TOTP_TRUST_DAYS", TRUST_DAYS_DEFAULT) or TRUST_DAYS_DEFAULT)


def generate_token():
    """A fresh 64-hex-char (256-bit) trust token for a new cookie."""
    return token_hex(32)


def hash_token(token):
    """Deterministic digest stored in the DB (sha256 of the raw token)."""
    return hashlib.sha256((token or "").encode()).hexdigest()


def device_label(user_agent):
    """Turn a raw User-Agent into a short human label like 'Chrome on Windows'."""
    ua = user_agent or ""
    if "Edg/" in ua:
        browser = "Edge"
    elif "Chrome/" in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "Browser"
    if "Windows" in ua:
        os_name = "Windows"
    elif "Macintosh" in ua or "Mac OS" in ua:
        os_name = "macOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Unknown OS"
    return f"{browser} on {os_name}"


def client_ip(request):
    """Best-effort client IP (honours X-Forwarded-For, like the rate limiter)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45] or None
    return request.META.get("REMOTE_ADDR") or None


def check_trust(request, user):
    """Return True if ``user`` has a valid unexpired trust cookie on this browser.

    Also bumps ``last_used_at`` (throttled) so the Settings list reflects
    real usage without writing on every login.
    """
    token = request.COOKIES.get(TRUST_COOKIE_NAME)
    if not token or user is None or not getattr(user, "is_authenticated", False):
        return False
    digest = hash_token(token)
    # Lazy housekeeping: sweep this user's expired rows on ~1% of checks so
    # devices for users who never re-issue a cookie don't pile up forever.
    if random.random() < 0.01:
        TrustedDevice.objects.filter(user=user, expires_at__lte=timezone.now()).delete()
    device = (
        TrustedDevice.objects.filter(user=user, token_hash=digest)
        .filter(expires_at__gt=timezone.now())
        .first()
    )
    if device is None:
        return False
    now = timezone.now()
    if not device.last_used_at or now - device.last_used_at > _LAST_USED_WRITE_WINDOW:
        TrustedDevice.objects.filter(pk=device.pk).update(last_used_at=now)
    return True


def issue_trust(response, request, user):
    """Record a new trusted device and set the trust cookie on ``response``.

    Housekeeping: expired rows for this user are deleted when a new device is
    added, so the table doesn't grow forever.
    """
    token = generate_token()
    now = timezone.now()
    expires_at = now + timedelta(days=trust_days())
    TrustedDevice.objects.filter(user=user, expires_at__lte=now).delete()
    TrustedDevice.objects.create(
        user=user,
        token_hash=hash_token(token),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
        ip_address=client_ip(request),
        last_used_at=now,
        expires_at=expires_at,
    )
    response.set_cookie(
        TRUST_COOKIE_NAME,
        token,
        max_age=trust_days() * 24 * 3600,
        httponly=True,
        samesite="Lax",
        secure=bool(settings.SESSION_COOKIE_SECURE),
        path="/",
    )
    return response


def revoke_all(user):
    """Drop every trusted device for ``user`` (2FA disable / revoke-all)."""
    TrustedDevice.objects.filter(user=user).delete()
