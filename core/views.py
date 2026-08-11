from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_POST

from candidates.models import Candidate
from core.auth import admin_required
from core.email_utils import (
    parse_verification_token,
    send_verification_email,
    get_unverified_user_by_email,
)
from core.forms import (
    LoginForm,
    PasswordResetForm,
    ResendVerificationForm,
    SignupForm,
)
from core.ratelimit import (
    account_login_blocked,
    clear_account_lockout,
    clear_login_failures,
    login_failure_blocked,
    rate_limit,
    throttled_response,
)
from jobs.models import Job


# ---------------------------------------------------------------------------
# Authentication: signup + email verification (public) + role management (admin)
# ---------------------------------------------------------------------------
class LoginView(auth_views.LoginView):
    """Login that understands the email-verification state: when credentials
    are valid but the email is unverified, the template shows a "please
    verify" notice plus a resend form instead of a generic error.

    When the account has TOTP two-factor enabled, the password is verified
    but the user is NOT signed in: they are sent to the 2FA challenge page
    (``totp_challenge``) where the authenticator code is required. The
    pending identity is stashed in the session (id + auth backend) and only
    converted to a real login by the challenge view.
    """

    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        """Successful login: reset failure counters, then either finish the
        login or bounce to the TOTP challenge when 2FA is enabled."""
        username = form.cleaned_data.get("username", "")
        clear_login_failures(self.request, username)
        clear_account_lockout(username)
        user = form.get_user()
        if user.profile.totp_enabled:
            # A trusted browser ("remember this device" cookie issued after a
            # previous 2FA success) skips the challenge: the cookie is bound
            # to this user and device, so it can't be replayed across accounts.
            from core.trust import check_trust

            if check_trust(self.request, user):
                from core.security_log import log_event

                log_event(user, "login", self.request, detail="Trusted browser (2FA)")
                return super().form_valid(form)
            # Password correct - but 2FA stands between here and the app.
            # Preserve the ?next= target so the challenge success lands the
            # user where they were headed, not always the dashboard.
            next_url = self.request.POST.get("next") or self.request.GET.get("next") or ""
            self.request.session["totp_pending"] = {
                "user_id": user.pk,
                "backend": self.request.POST.get("backend")
                or "django.contrib.auth.backends.ModelBackend",
                "next": next_url,
            }
            self.request.session["totp_username"] = username
            return redirect("totp_challenge")
        # No 2FA: audit the sign-in (trusted vs new browser), and with
        # "notify me of new logins" on, email the user on untrusted devices.
        from core.email_utils import send_login_alert
        from core.security_log import log_event
        from core.trust import check_trust

        trusted = check_trust(self.request, user)
        log_event(user, "login", self.request, detail="Trusted browser" if trusted else "New browser")
        if user.profile.login_alerts_enabled and not trusted:
            send_login_alert(user, self.request)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        error_codes = {
            e.code
            for field in form.errors.values()
            for e in field.as_data()
        } if form else set()
        context["unverified"] = "unverified" in error_codes
        if context["unverified"]:
            context["resend_form"] = ResendVerificationForm()
        context["locked"] = "locked" in error_codes
        lockout_seconds = getattr(self, "_lockout_seconds", 0)
        context["lockout_minutes"] = max(1, -(-lockout_seconds // 60)) if lockout_seconds else 0
        return context

    def form_invalid(self, form):
        """Failed login: record the attempt and throttle brute-force.

        Three layers: the account lockout (per username, all IPs), then the
        per-IP+username and per-IP buckets. Only failures count (success
        resets), so legitimate users are never penalized — and the correct
        password always clears the lockout, so an attacker's noise can't
        lock out the real owner.
        """
        username = self.request.POST.get("username", "")

        # Account-level lockout first: when locked, show a friendly notice
        # with the remaining time instead of the generic error.
        locked, seconds = account_login_blocked(self.request, username)
        if locked:
            self._lockout_seconds = seconds
            form.add_error(None, forms.ValidationError(
                "Too many failed attempts — this account is temporarily locked.",
                code="locked",
            ))
            return super().form_invalid(form)

        blocked, retry_after = login_failure_blocked(self.request, username)
        if blocked:
            return throttled_response(self.request, retry_after)
        return super().form_invalid(form)


def _email_client_key(request):
    """Rate-limit email-triggering endpoints (resend, password reset) per IP
    *and* per submitted address, so a single account can't be flooded with
    emails from one source."""
    email = (request.POST.get("email") or "").strip().lower()
    ip = request.META.get("REMOTE_ADDR", "unknown")
    return f"{ip}|{email}"


class PasswordResetView(auth_views.PasswordResetView):
    """Forgot-password entry point: enter email, we send a reset link.

    Django's built-in machinery handles token generation + expiry; we swap
    in branded templates, our own email pipeline (SITE_URL absolute links)
    and a rate limit so the endpoint can't be used to flood inboxes.
    """

    template_name = "registration/password_reset_form.html"
    form_class = PasswordResetForm
    success_url = reverse_lazy("password_reset_done")

    @method_decorator(rate_limit("password_reset", key_func=_email_client_key))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    """'Check your inbox' page shown after requesting a reset. Deliberately
    identical whether or not the email exists (anti-enumeration)."""

    template_name = "registration/password_reset_done.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Same dev-mode hint as the verification "check your inbox" page:
        # with the console email backend the link prints to the terminal.
        context["dev_mode"] = settings.DEBUG
        return context


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """The emailed link lands here to set a new password.

    Rate limit covers the new-password POSTs (brute-forcing a short guessable
    password). Token *validity probing* via GET is unthrottled, but that is
    theoretical: tokens are signed with SECRET_KEY and high-entropy, so
    direct guessing is infeasible.
    """

    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    @method_decorator(rate_limit("password_reset_confirm"))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    """Success page after the password has been changed."""

    template_name = "registration/password_reset_complete.html"


class TotpCodeForm(forms.Form):
    """The 6-digit TOTP code entered on the 2FA challenge / setup pages."""

    code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )


class TotpChallengeView(View):
    """Second step of login when the account has TOTP 2FA enabled.

    Requires a pending login (password already verified, stashed in the
    session by LoginView). A correct code signs the user in; wrong codes are
    rate-limited per IP to blunt brute-forcing the 6 digits.
    """

    template_name = "registration/totp_challenge.html"

    def _pending(self, request):
        return request.session.get("totp_pending") or {}

    def _get_user(self, request):
        pending = self._pending(request)
        pk = pending.get("user_id")
        return User.objects.filter(pk=pk).first() if pk else None

    def get(self, request):
        user = self._get_user(request)
        if user is None:
            messages.error(request, "Your 2FA session expired — please sign in again.")
            return redirect("login")
        return render(request, self.template_name, {"challenge_user": user})

    @method_decorator(rate_limit("totp_challenge", key_func=lambda r: f"{r.META.get('REMOTE_ADDR', '?')}|{r.session.get('totp_username', '')}"))
    def post(self, request):
        user = self._get_user(request)
        if user is None:
            messages.error(request, "Your 2FA session expired — please sign in again.")
            return redirect("login")

        code = request.POST.get("code", "").strip()
        from core.totp import verify_code, verify_recovery_code

        # Accept either the live TOTP code or an unused one-time recovery code.
        authenticated = verify_code(user.profile.totp_secret, code) or verify_recovery_code(
            user.profile, code
        )
        if authenticated:
            pending = self._pending(request)
            auth_login(request, user, backend=pending.get("backend"))
            user.profile.totp_verified_at = timezone.now()
            user.profile.save(update_fields=["totp_verified_at", "updated_at"])
            next_url = pending.get("next") or ""
            request.session.pop("totp_pending", None)
            request.session.pop("totp_username", None)
            # Honor the original ?next= target; validate it to avoid open-redirect.
            if next_url.startswith("/") and not next_url.startswith("//"):
                response = redirect(next_url)
            else:
                response = redirect(settings.LOGIN_REDIRECT_URL)
            # Optional "trust this browser": the checkbox only works because
            # the 2FA code was just verified - the cookie records that.
            if request.POST.get("trust_device"):
                from core.trust import device_label, issue_trust

                issue_trust(response, request, user)
                from core.security_log import log_event

                log_event(
                    user,
                    "device_trusted",
                    request,
                    detail=device_label(request.META.get("HTTP_USER_AGENT", "")),
                )
            # This login came from an untrusted browser (the challenge only
            # runs when no trust cookie was valid) - alert if opted in, and
            # always audit it.
            from core.security_log import log_event
            from core.trust import device_label

            log_event(
                user,
                "2fa_login",
                request,
                detail=device_label(request.META.get("HTTP_USER_AGENT", "")),
            )
            if user.profile.login_alerts_enabled:
                from core.email_utils import send_login_alert

                send_login_alert(user, request)
            messages.success(
                request,
                f"Welcome back, {user.first_name or user.get_username()}! 2FA verified.",
            )
            return response

        form = TotpCodeForm(request.POST)
        form.add_error("code", "That code isn't valid. Check the time on your phone and try again.")
        return render(
            request,
            self.template_name,
            {"challenge_user": user, "form": form, "code": code},
        )


class TotpSetupView(LoginRequiredMixin, View):
    """Two-factor setup page (authenticated). Generates a secret, shows the
    QR code and the manual secret, and requires one valid code before the
    feature is enabled (proves the user actually scanned it).
    """

    template_name = "core/totp_setup.html"

    def get_context_data(self):
        request = self.request
        from core.totp import generate_secret, otpauth_uri, qr_svg, current_code

        secret = request.session.get("totp_setup_secret")
        if not secret:
            secret = generate_secret()
            request.session["totp_setup_secret"] = secret
        user = request.user
        context = {
            "active_page": "settings",
            "secret": secret,
            "qr_svg": qr_svg(secret, user),
            "manual_uri": otpauth_uri(secret, user),
            "enabled": user.profile.totp_enabled,
        }
        if user.profile.totp_enabled:
            # Trusted browsers that skip the challenge, newest first, with a
            # friendly "Chrome on Windows" label from the raw user-agent.
            from core.trust import device_label

            context["trusted_devices"] = [
                {
                    "pk": d.pk,
                    "label": device_label(d.user_agent) or "This device",
                    "ip_address": d.ip_address,
                    "created_at": d.created_at,
                    "expires_at": d.expires_at,
                }
                for d in user.trusted_devices.filter(expires_at__gt=timezone.now())[:10]
            ]
        return context

    def get(self, request):
        return render(request, self.template_name, self.get_context_data())

    def post(self, request):
        from core.totp import verify_code

        secret = request.session.get("totp_setup_secret")
        if not secret:
            return redirect("totp_setup")
        code = request.POST.get("code", "").strip()
        if verify_code(secret, code):
            profile = request.user.profile
            profile.totp_secret = secret
            profile.totp_enabled = True
            profile.totp_verified_at = timezone.now()
            # Issue a fresh batch of one-time recovery codes (stored hashed).
            from core.totp import generate_recovery_codes, hash_recovery_codes

            plain_codes = generate_recovery_codes()
            profile.recovery_codes = hash_recovery_codes(plain_codes)
            profile.recovery_codes_generated_at = timezone.now()
            profile.save(
                update_fields=[
                    "totp_secret", "totp_enabled", "totp_verified_at",
                    "recovery_codes", "recovery_codes_generated_at", "updated_at",
                ]
            )
            request.session.pop("totp_setup_secret", None)
            # The plaintext codes are shown exactly once, right now.
            request.session["recovery_codes_once"] = plain_codes
            from core.security_log import log_event

            log_event(request.user, "2fa_enabled", request)
            log_event(request.user, "recovery_codes_generated", request, detail=f"{len(plain_codes)} codes")
            messages.success(request, "Two-factor authentication is now ON. Save your recovery codes below!")
            return redirect("totp_recovery_codes")
        context = self.get_context_data()
        context["error"] = "That code isn't valid. Try again with the code currently shown in your app."
        return render(request, self.template_name, context)


@login_required
def totp_recovery_codes(request):
    """Show the freshly-issued recovery codes exactly once.

    The plaintext batch lives only in the session and is displayed on this
    page; after the first render it's gone (refresh shows the remaining
    count and a regenerate action instead).
    """
    once = request.session.pop("recovery_codes_once", None)
    profile = request.user.profile
    remaining = len(profile.recovery_codes or [])
    return render(
        request,
        "core/recovery_codes.html",
        {
            "active_page": "settings",
            "codes": once or [],
            "shown_once": once is not None,
            "remaining": remaining,
            "generated_at": profile.recovery_codes_generated_at,
        },
    )


@login_required
@require_POST
def totp_recovery_codes_regenerate(request):
    """Issue a fresh batch of recovery codes (requires 2FA enabled + password)."""
    profile = request.user.profile
    if not profile.totp_enabled:
        messages.error(request, "Enable two-factor authentication first.")
        return redirect("totp_setup")
    password = request.POST.get("password", "")
    if not request.user.check_password(password):
        messages.error(request, "Your password didn't match — recovery codes were not regenerated.")
        return redirect("totp_setup")
    from core.totp import generate_recovery_codes, hash_recovery_codes

    plain_codes = generate_recovery_codes()
    profile.recovery_codes = hash_recovery_codes(plain_codes)
    profile.recovery_codes_generated_at = timezone.now()
    profile.save(update_fields=["recovery_codes", "recovery_codes_generated_at", "updated_at"])
    request.session["recovery_codes_once"] = plain_codes
    from core.security_log import log_event

    log_event(request.user, "recovery_codes_regenerated", request, detail=f"{len(plain_codes)} codes")
    messages.success(request, "New recovery codes generated — save them somewhere safe.")
    return redirect("totp_recovery_codes")


@login_required
@require_POST
def totp_disable(request):
    """Turn off 2FA (authenticated). Requires confirming the account password
    so a stolen session can't silently downgrade security."""
    password = request.POST.get("password", "")
    if not request.user.check_password(password):
        messages.error(request, "Your password didn't match — 2FA was not disabled.")
        return redirect("totp_setup")
    profile = request.user.profile
    profile.totp_enabled = False
    profile.totp_secret = None
    profile.totp_verified_at = None
    # Wipe recovery codes too - they're meaningless once 2FA is off.
    profile.recovery_codes = []
    profile.recovery_codes_generated_at = None
    profile.save(
        update_fields=[
            "totp_enabled", "totp_secret", "totp_verified_at",
            "recovery_codes", "recovery_codes_generated_at", "updated_at",
        ]
    )
    # Trusted-device cookies are meaningless once 2FA is off - wipe them so a
    # stale cookie can't skip a (future) re-enabled 2FA.
    from core.trust import TRUST_COOKIE_NAME, revoke_all

    revoke_all(request.user)
    from core.security_log import log_event

    log_event(request.user, "2fa_disabled", request)
    response = redirect("password_change")
    response.delete_cookie(TRUST_COOKIE_NAME)
    messages.success(request, "Two-factor authentication is now OFF.")
    return response


def _other_session_keys(user, current_key, limit=None):
    """Session keys of the user's *other* active sessions.

    Scans the DB session table (the default SESSION_ENGINE) and decodes each
    row to find those owned by ``user`` - the approach Django documents for
    "sign out this user everywhere". Returns the keys excluding the current
    browser's session. ``limit`` bounds the scan (used by the read-only
    count on the log page); the sign-out POST never limits, so it always
    clears every session.
    """
    from django.contrib.sessions.models import Session

    if not current_key:
        # Can't identify the current session - refuse to delete anything
        # rather than risk signing the user out of their own browser.
        return []
    qs = Session.objects.filter(expire_date__gt=timezone.now())
    if limit:
        qs = qs[:limit]
    user_id = str(user.pk)
    keys = []
    for session in qs:
        if (
            session.session_key != current_key
            and session.get_decoded().get("_auth_user_id") == user_id
        ):
            keys.append(session.session_key)
    return keys


@login_required
@require_POST
def sign_out_other_sessions(request):
    """Sign out every session except the current browser's.

    The natural companion to the security log: spot a login you didn't make,
    then kill it (and everything else) in one click. Logs the event so the
    action itself is audited.
    """
    from django.contrib.sessions.models import Session

    keys = _other_session_keys(request.user, request.session.session_key)
    Session.objects.filter(session_key__in=keys).delete()

    from core.security_log import log_event

    log_event(request.user, "sessions_signed_out", request, detail=f"{len(keys)} session(s)")
    if keys:
        messages.success(request, f"Signed out {len(keys)} other session(s). You're still signed in here.")
    else:
        messages.info(request, "No other active sessions to sign out.")
    return redirect("security_log")


@login_required
def security_log(request):
    """Per-user security audit trail: sign-ins, 2FA changes, trusted-device
    events, recovery-code issuance, password changes and alert toggles."""
    from core.security_log import EVENT_LABELS, FILTER_GROUPS, filter_events

    # Optional ?filter= slug (signins | twofa | devices | account); anything
    # else - missing or bogus - falls back to "all" and can never hide events.
    slug = request.GET.get("filter", "all")
    if slug not in {key for key, _label, _events in FILTER_GROUPS}:
        slug = "all"
    # Slice 101 and derive `truncated` from the length - one query instead of
    # two (the slice's internal count + an explicit count).
    raw = list(filter_events(request.user.security_log.all(), slug)[:101])  # newest first (Meta ordering)
    truncated = len(raw) > 100
    events = [
        {
            "event": e.event,
            "label": EVENT_LABELS.get(e.event, e.event),
            "detail": e.detail,
            "created_at": e.created_at,
            "ip_address": e.ip_address,
        }
        for e in raw[:100]
    ]
    # Cosmetic count only - bound the scan so a big session table can't slow
    # the page; past 100 we just show "100+".
    other_keys = _other_session_keys(
        request.user, request.session.session_key, limit=101
    )
    other_session_count = min(len(other_keys), 100)
    return render(
        request,
        "core/security_log.html",
        {
            "active_page": "settings",
            "events": events,
            "truncated": truncated,
            "filters": [(key, label) for key, label, _events in FILTER_GROUPS],
            "active_filter": slug,
            "active_label": next(
                (label for key, label, _events in FILTER_GROUPS if key == slug), "All"
            ),
            "other_sessions": other_session_count,
            "other_sessions_plus": other_session_count > 100,
        },
    )


@login_required
@require_POST
def login_alerts_toggle(request):
    """Flip the "notify me of new logins" setting from the Settings page."""
    profile = request.user.profile
    profile.login_alerts_enabled = request.POST.get("enabled") == "on"
    profile.save(update_fields=["login_alerts_enabled", "updated_at"])
    from core.security_log import log_event

    log_event(
        request.user,
        "alerts_toggled",
        request,
        detail="turned on" if profile.login_alerts_enabled else "turned off",
    )
    state = "ON — you'll get an email after any sign-in from a new device" if profile.login_alerts_enabled else "OFF"
    messages.success(request, f"Sign-in alerts are now {state}.")
    return redirect("password_change")


@login_required
@require_POST
def totp_trust_revoke(request, pk):
    """Forget one trusted device. Only the owner can revoke their own."""
    device = get_object_or_404(request.user.trusted_devices, pk=pk)
    device.delete()
    # If the revoked device is this browser, drop its (now useless) cookie too.
    response = redirect("totp_setup")
    from core.security_log import log_event
    from core.trust import TRUST_COOKIE_NAME, device_label, hash_token

    log_event(
        request.user,
        "device_revoked",
        request,
        # UA-less devices get the same "This device" default as the UI.
        detail=device_label(device.user_agent) if device.user_agent else "This device",
    )
    cookie = request.COOKIES.get(TRUST_COOKIE_NAME)
    if cookie and hash_token(cookie) == device.token_hash:
        response.delete_cookie(TRUST_COOKIE_NAME)
    messages.success(request, "That device was forgotten — 2FA will be required there again.")
    return response


@login_required
@require_POST
def totp_trust_revoke_all(request):
    """Forget every trusted device: 2FA challenge on all browsers from now on."""
    from core.trust import TRUST_COOKIE_NAME, revoke_all

    revoke_all(request.user)
    # This browser is one of the devices being forgotten.
    from core.security_log import log_event

    log_event(request.user, "devices_revoked_all", request)
    response = redirect("totp_setup")
    response.delete_cookie(TRUST_COOKIE_NAME)
    messages.success(request, "All trusted devices were forgotten.")
    return response


class PasswordChangeView(auth_views.PasswordChangeView):
    """Authenticated users change their own password from the Settings page.

    Uses Django's battle-tested form (old-password check + the same
    strong-password validators as signup/reset, enforced server-side) and the
    live strength meter on the new-password field. On success the user stays
    on the page with a toast; all other sessions are invalidated.
    """

    template_name = "core/password_change.html"
    success_url = reverse_lazy("password_change")

    def form_valid(self, form):
        response = super().form_valid(form)
        from core.security_log import log_event

        log_event(self.request.user, "password_changed", self.request)
        messages.success(
            self.request,
            "Your password has been changed. You'll need to sign in again on your other devices.",
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_page"] = "settings"
        return context


@rate_limit("signup")
def signup(request):
    """Self-registration. New accounts are created as Recruiters with an
    unverified email, then a welcome + verification email is sent. They must
    click the link before their first login. The Admin role is admin-managed.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            name = user.get_full_name() or user.get_username()
            sent = send_verification_email(user, request=request)
            if sent:
                messages.success(
                    request,
                    f"Welcome to TalentPulse, {name}! We sent a verification link to {user.email}.",
                )
            else:
                messages.warning(
                    request,
                    f"Welcome to TalentPulse, {name}! We couldn't send the verification email right now — use the resend box on the next page.",
                )
            return redirect("verify_email_sent")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


def verify_email_sent(request):
    """"Check your inbox" landing page shown right after signup."""
    return render(
        request,
        "registration/verify_email_sent.html",
        # In dev (console backend) the link prints to the terminal, so the
        # page can tell the user where to find it.
        {"dev_mode": settings.DEBUG},
    )


def verify_email(request, token):
    """Handle the signed link from the welcome email. Marks the account
    verified, then points the user at the login page.
    """
    pk = parse_verification_token(token)
    user = User.objects.select_related("profile").filter(pk=pk).first() if pk else None
    status = "success"
    if user is None:
        status = "invalid"
    elif user.profile.is_verified:
        status = "already"
    else:
        user.profile.email_verified = True
        user.profile.save(update_fields=["email_verified", "updated_at"])
        messages.success(
            request,
            f"Your email is verified — welcome to TalentPulse, {user.first_name or user.get_username()}! 🎉",
        )
    return render(request, "registration/verify_email_result.html", {"status": status})


@rate_limit("resend", key_func=_email_client_key)
@require_POST
def verify_email_resend(request):
    """Re-send the verification email for an unverified account.

    Deliberately responds the same way whether or not the email belongs to a
    pending account, so the endpoint can't be used to probe for signups.
    """
    form = ResendVerificationForm(request.POST)
    user = None
    if form.is_valid():
        # NOTE: timing — this branch does real work (render + send) only when
        # a matching pending account exists, so response time can leak account
        # existence despite the identical message below. Acceptable for this
        # demo; a no-op send would mask it if that ever matters.
        user = get_unverified_user_by_email(form.cleaned_data["email"])
        if user:
            send_verification_email(user, request=request)
    messages.success(
        request,
        "If that address has a pending account, a fresh verification link is on its way.",
    )
    # Return the admin to the Users page when triggered from there; otherwise
    # fall back to the login page.
    referer = request.META.get("HTTP_REFERER", "")
    if referer and "/users/" in referer:
        return redirect("user_list")
    return redirect("login")


@admin_required
def user_list(request):
    """Admin-only: all workspace accounts with their roles and status.

    Supports optional GET filters: ?role=admin|recruiter and
    ?status=active|disabled. A quick client-side search box on the page
    filters rows instantly without a round-trip.
    """
    users = User.objects.select_related("profile").all()

    role = request.GET.get("role", "")
    if role == "admin":
        users = users.filter(is_superuser=True)
    elif role == "recruiter":
        users = users.filter(is_superuser=False)
    else:
        role = ""

    status = request.GET.get("status", "")
    if status == "active":
        users = users.filter(is_active=True)
    elif status == "disabled":
        users = users.filter(is_active=False)
    else:
        status = ""

    users = users.order_by("-is_superuser", "username").all()
    context = {
        "active_page": "users",
        "users": users,
        "role": role,
        "status": status,
    }
    return render(request, "users.html", context)


@admin_required
@require_POST
def user_toggle_role(request, pk):
    """Promote a recruiter to Admin, or demote an Admin back to Recruiter.

    The only guard needed is that you cannot change your own role: because
    this view requires an Admin actor, demoting someone else always leaves
    the actor as an Admin, so the workspace can never lose its last Admin.
    """
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, "You cannot change your own role.")
        return redirect("user_list")
    target.is_superuser = not target.is_superuser
    target.is_staff = target.is_superuser
    target.save(update_fields=["is_superuser", "is_staff"])
    role = "Admin" if target.is_superuser else "Recruiter"
    messages.success(request, f"{target.get_username()} is now {role}.")
    return redirect("user_list")


@admin_required
@require_POST
def user_toggle_active(request, pk):
    """Activate or deactivate an account. You cannot deactivate yourself."""
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("user_list")
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    state = "reactivated" if target.is_active else "deactivated"
    messages.success(request, f"{target.get_username()} has been {state}.")
    return redirect("user_list")


@login_required
@require_GET
def command_search(request):
    """Global search for the command palette.

    Returns matching candidates, jobs and static quick actions as JSON so the
    front-end can render an instant, keyboard-navigable palette.
    """
    q = (request.GET.get("q") or "").strip()
    limit = 6

    candidates = []
    if q:
        candidates = list(
            Candidate.objects.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
                | Q(headline__icontains=q)
            )
            .order_by("-created_at")[:limit]
        )

    jobs = []
    if q:
        jobs = list(
            Job.objects.filter(
                Q(title__icontains=q)
                | Q(department__icontains=q)
                | Q(location__icontains=q)
            )
            .order_by("-created_at")[:limit]
        )

    actions = [
        {"label": "Dashboard", "hint": "Go to overview", "url": "/"},
        {"label": "Jobs", "hint": "All open positions", "url": "/jobs/"},
        {"label": "Candidates", "hint": "Talent pool", "url": "/candidates/"},
        {"label": "Pipeline", "hint": "Kanban board", "url": "/pipeline/"},
        {"label": "Interviews", "hint": "Scheduled interviews", "url": "/interviews/"},
        {"label": "New job", "hint": "Create a requisition", "url": "/jobs/new/"},
        {"label": "Add candidate", "hint": "Create a profile", "url": "/candidates/new/"},
    ]
    if q:
        actions = [
            a for a in actions
            if q.lower() in a["label"].lower() or q.lower() in a["hint"].lower()
        ]

    return JsonResponse({
        "query": q,
        "actions": actions,
        "candidates": [
            {
                "label": c.full_name,
                "hint": f"{c.headline or 'Candidate'} · {c.email}",
                "url": f"/candidates/{c.pk}/",
                "meta": "candidate",
                "initials": c.initials,
            }
            for c in candidates
        ],
        "jobs": [
            {
                "label": j.title,
                "hint": f"{j.department or 'General'} · {j.location or 'Remote'}",
                "url": f"/jobs/{j.pk}/",
                "meta": "job",
            }
            for j in jobs
        ],
    })
