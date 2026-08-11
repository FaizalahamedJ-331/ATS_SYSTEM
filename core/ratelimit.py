"""Lightweight sliding-window rate limiting for public endpoints.

Uses Django's cache framework (LocMemCache by default in development; point
CACHES at a shared backend like Redis or a DB cache in production). No extra
dependencies. Applied with a decorator:

    @rate_limit("signup")
    def signup(request): ...

Limits come from settings at request time — ``<KEY>_RATE_LIMIT`` and
``<KEY>_RATE_WINDOW`` (e.g. ``SIGNUP_RATE_LIMIT``), so they can be tuned via
environment variables and overridden in tests without a restart.

Keys are namespaced per client (IP by default; pass a custom key function to
include e.g. the submitted email so a single account can't be hammered).

Login is special-cased: brute-force protection counts *failed* attempts only
(per IP+username, plus a per-IP cap for username spraying) and resets on a
successful login, so a legitimate user who mistypes a few times is never
locked out.
"""
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render


def _window_check(cache_key, max_requests, window_seconds, now=None):
    """Sliding-window check + record.

    Returns ``(allowed, retry_after)``. When over the limit the attempt is
    NOT recorded, so hammering never extends the lockout — the window only
    clears once the oldest hits age out.
    """
    now = now if now is not None else time.time()
    hits = [t for t in (cache.get(cache_key) or []) if now - t < window_seconds]

    if len(hits) >= max_requests:
        # hits is empty only when max_requests is 0 (misconfiguration);
        # fall back to the full window in that case.
        oldest = hits[0] if hits else now
        retry_after = max(1, int(window_seconds - (now - oldest)) + 1)
        return False, retry_after

    hits.append(now)
    cache.set(cache_key, hits, window_seconds)
    return True, 0


def throttled_response(request, retry_after):
    """Branded 429 page with a real Retry-After header."""
    response = render(
        request,
        "429.html",
        {"retry_after": retry_after},
        status=429,
    )
    response["Retry-After"] = str(retry_after)
    return response


def rate_limit(key, key_func=None):
    """Decorator: allow at most ``<KEY>_RATE_LIMIT`` POSTs per client per
    window of ``<KEY>_RATE_WINDOW`` seconds.

    Only POST requests are counted (the endpoints being protected are
    state-changing). When the limit is hit a branded 429 page is rendered.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.method != "POST":
                return view_func(request, *args, **kwargs)

            max_requests = getattr(settings, f"{key.upper()}_RATE_LIMIT", 5)
            window_seconds = getattr(settings, f"{key.upper()}_RATE_WINDOW", 3600)

            client = key_func(request) if key_func else request.META.get("REMOTE_ADDR", "unknown")
            allowed, retry_after = _window_check(
                f"rl:{key}:{client}", max_requests, window_seconds
            )
            if not allowed:
                return throttled_response(request, retry_after)

            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def login_failure_blocked(request, username):
    """Record a failed login attempt; return ``(blocked, retry_after)``.

    Two buckets:
    - ``LOGIN_RATE_LIMIT`` per IP+username (blocks brute-forcing one
      account from one source),
    - ``LOGIN_IP_RATE_LIMIT`` per IP (blocks username spraying — many
      accounts tried from the same source).

    Returns blocked=True and the retry-after hint once either is exceeded.
    """
    ip = request.META.get("REMOTE_ADDR", "unknown")
    uname = (username or "").strip().lower()

    user_key = f"rl:login:user:{ip}|{uname}"
    ip_key = f"rl:login:ip:{ip}"

    # Form-validation failures (e.g. empty username) never reached
    # authentication — don't let them eat the budget, or a spammer could
    # exhaust the per-IP spray cap with cheap garbage requests.
    if not (username or "").strip():
        return False, 0

    user_limit = getattr(settings, "LOGIN_RATE_LIMIT", 5)
    ip_limit = getattr(settings, "LOGIN_IP_RATE_LIMIT", 20)
    window = getattr(settings, "LOGIN_RATE_WINDOW", 900)

    # Check the IP cap first so a blocked (spray-limited) attempt doesn't
    # also consume a per-username slot.
    allowed, retry_after = _window_check(ip_key, ip_limit, window)
    if not allowed:
        return True, retry_after

    allowed, retry_after = _window_check(user_key, user_limit, window)
    if not allowed:
        return True, retry_after

    return False, 0


def clear_login_failures(request, username):
    """Reset the failure counters after a successful login, so a few typos
    never compound into a lockout for a real user."""
    ip = request.META.get("REMOTE_ADDR", "unknown")
    uname = (username or "").strip().lower()
    cache.delete(f"rl:login:user:{ip}|{uname}")
    cache.delete(f"rl:login:ip:{ip}")


# ---------------------------------------------------------------------------
# Account lockout — distributed brute-force protection
# ---------------------------------------------------------------------------
# The per-IP buckets above stop a single source; an attacker rotating IPs can
# still probe one account many times. The account lockout counts failures
# against the *username* across all IPs and, once the threshold is hit, holds
# the account locked for a cooldown. Crucially, a successful login (correct
# password) always clears the lockout, so a legitimate owner is never locked
# out by an attacker's noise — and a brute-forcer can't produce the correct
# password anyway.

def account_lockout_info(username):
    """Return (locked, seconds_remaining) for this username, 0 when free."""
    uname = (username or "").strip().lower()
    if not uname:
        return False, 0
    now = time.time()
    state = cache.get(f"rl:lockout:{uname}") or {}
    locked_until = state.get("locked_until", 0)
    if locked_until and now < locked_until:
        return True, max(1, int(locked_until - now) + 1)
    return False, 0


def account_login_blocked(request, username):
    """Record a failed login against the account and return whether it is
    now (or already was) locked, plus seconds remaining.

    Failures are counted per username across all IPs within
    ``ACCOUNT_LOCKOUT_WINDOW`` seconds; when the count reaches
    ``ACCOUNT_LOCKOUT_LIMIT`` the account locks for ``ACCOUNT_LOCKOUT_COOLDOWN``
    seconds. Locked accounts return True and do NOT accumulate further hits,
    so hammering can't extend the lockout.
    """
    uname = (username or "").strip().lower()
    if not uname:
        return False, 0

    key = f"rl:lockout:{uname}"
    limit = getattr(settings, "ACCOUNT_LOCKOUT_LIMIT", 10)
    window = getattr(settings, "ACCOUNT_LOCKOUT_WINDOW", 900)
    cooldown = getattr(settings, "ACCOUNT_LOCKOUT_COOLDOWN", 900)

    now = time.time()
    state = cache.get(key) or {}

    # Already locked — never extend the lockout, never record more hits.
    locked, remaining = account_lockout_info(username)
    if locked:
        return True, remaining

    hits = [t for t in state.get("hits", []) if now - t < window]
    hits.append(now)

    if len(hits) >= limit:
        cache.set(key, {"hits": hits, "locked_until": now + cooldown}, cooldown)
        return True, cooldown

    cache.set(key, {"hits": hits}, window)
    return False, 0


def clear_account_lockout(username):
    """Reset the account lockout after a successful login."""
    uname = (username or "").strip().lower()
    if uname:
        cache.delete(f"rl:lockout:{uname}")
