"""Tests for the per-user security audit log (2FA + trusted-device events)."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import SecurityLog, TrustedDevice
from core.security_log import MAX_EVENTS_PER_USER, log_event
from core.totp import current_code, generate_secret
from core.trust import TRUST_COOKIE_NAME, generate_token, hash_token

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"


def event_names(user):
    return list(user.security_log.values_list("event", flat=True))


@override_settings(TOTP_CHALLENGE_RATE_LIMIT=100, TOTP_CHALLENGE_RATE_WINDOW=900)
class SecurityLogTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="secloguser", password="CorrectPass123!", email="sec@example.com"
        )
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])

    def _enable_2fa(self):
        self.user.profile.totp_secret = generate_secret()
        self.user.profile.totp_enabled = True
        self.user.profile.save(update_fields=["totp_secret", "totp_enabled"])

    def _complete_setup(self):
        """Drive the real 2FA setup flow (GET secret -> POST code)."""
        self.client.force_login(self.user)
        self.client.get(reverse("totp_setup"))
        secret = self.client.session["totp_setup_secret"]
        return self.client.post(reverse("totp_setup"), {"code": current_code(secret)})

    def _complete_challenge(self, trust=False):
        self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        data = {"code": current_code(self.user.profile.totp_secret)}
        if trust:
            data["trust_device"] = "on"
        return self.client.post(
            reverse("totp_challenge"), data, HTTP_USER_AGENT=CHROME_UA
        )

    # ------------------------------------------------------------- event capture

    def test_2fa_enable_logs(self):
        self._complete_setup()
        names = event_names(self.user)
        self.assertIn("2fa_enabled", names)
        self.assertIn("recovery_codes_generated", names)

    def test_2fa_disable_logs(self):
        self._enable_2fa()
        self.client.force_login(self.user)
        self.client.post(reverse("totp_disable"), {"password": "CorrectPass123!"})
        self.assertIn("2fa_disabled", event_names(self.user))

    def test_challenge_success_logs_with_device(self):
        self._enable_2fa()
        self._complete_challenge()
        entry = self.user.security_log.get(event="2fa_login")
        self.assertIn("Chrome on Windows", entry.detail)
        self.assertEqual(entry.ip_address, "127.0.0.1")

    def test_trust_device_logs(self):
        self._enable_2fa()
        self._complete_challenge(trust=True)
        self.assertIn("device_trusted", event_names(self.user))
        self.assertIn("2fa_login", event_names(self.user))

    def test_revoke_device_logs(self):
        self._enable_2fa()
        self.client.force_login(self.user)
        device = TrustedDevice.objects.create(
            user=self.user,
            token_hash=hash_token(generate_token()),
            user_agent=CHROME_UA,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.client.post(reverse("totp_trust_revoke", args=[device.pk]))
        entry = self.user.security_log.get(event="device_revoked")
        self.assertIn("Chrome on Windows", entry.detail)

    def test_revoke_all_logs(self):
        self.client.force_login(self.user)
        self.client.post(reverse("totp_trust_revoke_all"))
        self.assertIn("devices_revoked_all", event_names(self.user))

    def test_recovery_regenerate_logs(self):
        self._enable_2fa()
        self.client.force_login(self.user)
        self.client.post(
            reverse("totp_recovery_codes_regenerate"), {"password": "CorrectPass123!"}
        )
        entry = self.user.security_log.get(event="recovery_codes_regenerated")
        self.assertIn("8 codes", entry.detail)

    def test_password_change_logs(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("password_change"),
            {
                "old_password": "CorrectPass123!",
                "new_password1": "NewStrongPass456!",
                "new_password2": "NewStrongPass456!",
            },
        )
        self.assertIn("password_changed", event_names(self.user))

    def test_alerts_toggle_logs(self):
        self.client.force_login(self.user)
        self.client.post(reverse("login_alerts_toggle"), {"enabled": "on"})
        entry = self.user.security_log.get(event="alerts_toggled")
        self.assertEqual(entry.detail, "turned on")

    def test_login_logged_new_vs_trusted(self):
        # New browser -> logged as such.
        self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        entry = self.user.security_log.get(event="login")
        self.assertEqual(entry.detail, "New browser")
        # Trusted browser -> silent-ish "Trusted browser".
        token = generate_token()
        TrustedDevice.objects.create(
            user=self.user,
            token_hash=hash_token(token),
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.client.cookies[TRUST_COOKIE_NAME] = token
        self.client.post(reverse("logout"))
        self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        entries = self.user.security_log.filter(event="login")
        self.assertEqual(entries[0].detail, "Trusted browser")
        self.assertEqual(entries[1].detail, "New browser")

    # ------------------------------------------------------------- page + privacy

    def test_page_lists_own_events_newest_first(self):
        self.client.force_login(self.user)
        log_event(self.user, "password_changed")
        log_event(self.user, "2fa_enabled")
        response = self.client.get(reverse("security_log"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Password changed", html)
        self.assertIn("Two-factor authentication enabled", html)
        # Newest first: the later event appears before the earlier one.
        self.assertLess(html.index("Two-factor authentication enabled"), html.index("Password changed"))

    def test_page_hides_other_users_events(self):
        other = User.objects.create_user(
            username="seclogother", password="CorrectPass123!", email="so@example.com"
        )
        log_event(other, "password_changed", detail="someone else")
        log_event(other, "2fa_enabled")
        self.client.force_login(self.user)
        response = self.client.get(reverse("security_log"))
        html = response.content.decode()
        self.assertIn("No security events yet", html)
        self.assertNotIn("someone else", html)

    def test_page_requires_login(self):
        response = self.client.get(reverse("security_log"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_empty_state(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("security_log"))
        self.assertContains(response, "No security events yet")

    # ------------------------------------------------------------- retention

    def test_log_capped_per_user(self):
        """Pruning is occasional (every ~50th insert) so the cap is soft: it
        can briefly overshoot, then snaps back. Any 100 consecutive inserts
        hit at least two prune checks."""
        for i in range(MAX_EVENTS_PER_USER + 100):
            log_event(self.user, "login", detail=f"event {i}")
        # At least one prune fired: count is back near the cap.
        self.assertLessEqual(self.user.security_log.count(), MAX_EVENTS_PER_USER + 50)
        # Oldest events were pruned (newest survive).
        self.assertFalse(
            SecurityLog.objects.filter(user=self.user, detail="event 0").exists()
        )
        self.assertEqual(self.user.security_log.first().detail, f"event {MAX_EVENTS_PER_USER + 99}")

    def test_log_event_never_raises(self):
        # None user -> None, no exception.
        self.assertIsNone(log_event(None, "login"))
        # Other users are unaffected by our rows.
        other = User.objects.create_user(username="seclogcap", password="CorrectPass123!")
        self.assertEqual(other.security_log.count(), 0)

    def test_log_event_never_raises_on_db_failure(self):
        """Auditing must never break a login/2FA flow: a failing insert is
        swallowed and returns None."""
        from unittest import mock

        with mock.patch(
            "core.security_log.SecurityLog.objects.create",
            side_effect=RuntimeError("db down"),
        ):
            self.assertIsNone(log_event(self.user, "login"))

    def test_failed_login_logs_nothing(self):
        """Wrong passwords and lockouts stay out of the audit trail - it
        records successful sign-ins only (no noise)."""
        for _ in range(3):
            self.client.post(
                reverse("login"),
                {"username": self.user.username, "password": "WrongPass123!"},
            )
        self.assertEqual(self.user.security_log.count(), 0)

    # ------------------------------------------------------------- filtering

    def test_filter_signins(self):
        log_event(self.user, "login", detail="New browser")
        log_event(self.user, "2fa_enabled")
        self.client.force_login(self.user)
        response = self.client.get(reverse("security_log"), {"filter": "signins"})
        html = response.content.decode()
        self.assertIn("Signed in", html)
        self.assertNotIn("Two-factor authentication enabled", html)

    def test_filter_devices(self):
        log_event(self.user, "device_trusted", detail="Chrome on Windows")
        log_event(self.user, "login", detail="New browser")
        self.client.force_login(self.user)
        response = self.client.get(reverse("security_log"), {"filter": "devices"})
        html = response.content.decode()
        self.assertIn("Browser trusted for 30 days", html)
        self.assertNotIn("Signed in", html)

    def test_filter_twofa_and_codes(self):
        log_event(self.user, "2fa_disabled")
        log_event(self.user, "recovery_codes_regenerated")
        log_event(self.user, "login")
        self.client.force_login(self.user)
        response = self.client.get(reverse("security_log"), {"filter": "twofa"})
        html = response.content.decode()
        self.assertIn("Two-factor authentication disabled", html)
        self.assertIn("Recovery codes regenerated", html)
        self.assertNotIn("Signed in", html)

    def test_invalid_filter_falls_back_to_all(self):
        """A tampered ?filter= can never hide events - unknown slugs show all."""
        log_event(self.user, "login")
        log_event(self.user, "2fa_enabled")
        self.client.force_login(self.user)
        response = self.client.get(reverse("security_log"), {"filter": "bogus"})
        html = response.content.decode()
        self.assertIn("Signed in", html)
        self.assertIn("Two-factor authentication enabled", html)

    def test_filter_chips_render_with_active_state(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("security_log"), {"filter": "devices"})
        html = response.content.decode()
        for label in ("All", "Sign-ins", "Devices", "Account"):
            self.assertIn(label, html)
        self.assertIn("2FA &amp; codes", html)  # & is HTML-escaped
        self.assertIn("?filter=devices", html)
        self.assertIn("chip-active", html)

    def test_filtered_empty_state(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("security_log"), {"filter": "signins"})
        self.assertContains(response, "No Sign-ins events yet")

    # ------------------------------------------------------------- sign out

    def test_sign_out_other_sessions(self):
        from django.test import Client

        # Current browser (client A) + a real second session (client B).
        self.client.force_login(self.user)
        other = Client()
        other.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        self.assertIsNotNone(other.session.session_key)
        # The log page reports the other session.
        resp = self.client.get(reverse("security_log"))
        self.assertContains(resp, "1 other active session")
        # Sign out everywhere else.
        resp = self.client.post(reverse("sign_out_other_sessions"))
        self.assertEqual(resp.status_code, 302)
        # Client B is now signed out.
        r = other.get(reverse("password_change"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r.url)
        # Client A is still signed in.
        self.assertTrue(self.client.session.get("_auth_user_id"))
        # The action itself is audited.
        entry = self.user.security_log.get(event="sessions_signed_out")
        self.assertEqual(entry.detail, "1 session(s)")

    def test_sign_out_requires_login(self):
        response = self.client.post(reverse("sign_out_other_sessions"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_sign_out_with_no_other_sessions(self):
        self.client.force_login(self.user)
        self.client.post(reverse("sign_out_other_sessions"))
        # Current session survives and the (zero-count) event is logged.
        self.assertTrue(self.client.session.get("_auth_user_id"))
        entry = self.user.security_log.get(event="sessions_signed_out")
        self.assertEqual(entry.detail, "0 session(s)")

    def test_count_pluralizes_with_multiple_sessions(self):
        from django.test import Client

        self.client.force_login(self.user)
        c2 = Client()
        c2.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        c3 = Client()
        c3.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        resp = self.client.get(reverse("security_log"))
        self.assertContains(resp, "2 other active sessions")
