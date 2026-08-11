"""Tests for the opt-in "notify me of new logins" email alerts."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import TrustedDevice
from core.totp import current_code, generate_secret
from core.trust import TRUST_COOKIE_NAME, generate_token, hash_token

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"


@override_settings(TOTP_CHALLENGE_RATE_LIMIT=100, TOTP_CHALLENGE_RATE_WINDOW=900)
class LoginAlertTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.user = User.objects.create_user(
            username="alertuser", password="CorrectPass123!", email="alert@example.com"
        )
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])

    def _enable_alerts(self, on=True):
        self.user.profile.login_alerts_enabled = on
        self.user.profile.save(update_fields=["login_alerts_enabled"])

    def _enable_2fa(self):
        self.user.profile.totp_secret = generate_secret()
        self.user.profile.totp_enabled = True
        self.user.profile.save(update_fields=["totp_secret", "totp_enabled"])

    def _trust_cookie(self):
        """Seed a valid trust device + cookie for the user (works without 2FA)."""
        token = generate_token()
        TrustedDevice.objects.create(
            user=self.user,
            token_hash=hash_token(token),
            user_agent=CHROME_UA,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.client.cookies[TRUST_COOKIE_NAME] = token

    def _login(self):
        return self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
            HTTP_USER_AGENT=CHROME_UA,
        )

    # ------------------------------------------------------------- toggle

    def test_toggle_on(self):
        self.client.force_login(self.user)
        self.client.post(reverse("login_alerts_toggle"), {"enabled": "on"})
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.login_alerts_enabled)

    def test_toggle_off(self):
        self._enable_alerts(True)
        self.client.force_login(self.user)
        self.client.post(reverse("login_alerts_toggle"))  # checkbox absent
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.login_alerts_enabled)

    # ------------------------------------------------------------- no-2FA logins

    def test_untrusted_login_sends_alert(self):
        self._enable_alerts(True)
        response = self._login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("New sign-in to your TalentPulse account", msg.subject)
        self.assertIn("Chrome on Windows", msg.body)
        self.assertIn("127.0.0.1", msg.body)
        self.assertIn(" at ", msg.body)  # date filter renders cleanly (no escape artifacts)
        self.assertEqual(msg.to, ["alert@example.com"])

    def test_alerts_off_by_default_no_email(self):
        response = self._login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_trusted_login_silent(self):
        self._enable_alerts(True)
        self._trust_cookie()
        response = self._login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    # ------------------------------------------------------------- 2FA paths

    def test_2fa_challenge_success_alerts(self):
        self._enable_alerts(True)
        self._enable_2fa()
        response = self._login()
        self.assertEqual(response.url, reverse("totp_challenge"))
        self.assertEqual(len(mail.outbox), 0)  # alert waits until 2FA completes
        code = current_code(self.user.profile.totp_secret)
        response = self.client.post(
            reverse("totp_challenge"),
            {"code": code},
            HTTP_USER_AGENT=CHROME_UA,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Chrome on Windows", mail.outbox[0].body)

    def test_2fa_challenge_success_silent_when_off(self):
        self._enable_2fa()
        self._login()
        code = current_code(self.user.profile.totp_secret)
        self.client.post(reverse("totp_challenge"), {"code": code})
        self.assertEqual(len(mail.outbox), 0)

    def test_2fa_trusted_skip_silent(self):
        self._enable_alerts(True)
        self._enable_2fa()
        self._trust_cookie()
        response = self._login()
        self.assertNotEqual(response.url, reverse("totp_challenge"))
        self.assertEqual(len(mail.outbox), 0)

    def test_settings_page_shows_toggle(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("password_change"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notify me of new logins")
        self.assertContains(response, reverse("login_alerts_toggle"))
