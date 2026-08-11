"""Tests for "remember this device" trust cookies that skip the 2FA challenge."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import TrustedDevice
from core.totp import current_code, generate_secret
from core.trust import (
    TRUST_COOKIE_NAME,
    check_trust,
    device_label,
    generate_token,
    hash_token,
    issue_trust,
)
from django.http import HttpResponse
from django.utils import timezone


@override_settings(TOTP_CHALLENGE_RATE_LIMIT=100, TOTP_CHALLENGE_RATE_WINDOW=900)
class TrustedDeviceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="trustuser", password="CorrectPass123!", email="trust@example.com"
        )
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])
        self._enable_2fa()

    def _enable_2fa(self):
        self.user.profile.totp_secret = generate_secret()
        self.user.profile.totp_enabled = True
        self.user.profile.save(update_fields=["totp_secret", "totp_enabled"])

    def _trusted_request(self):
        from django.test import RequestFactory

        token = generate_token()
        TrustedDevice.objects.create(
            user=self.user,
            token_hash=hash_token(token),
            expires_at=timezone.now() + timedelta(days=30),
            last_used_at=timezone.now(),
        )
        request = RequestFactory().get("/")
        request.COOKIES[TRUST_COOKIE_NAME] = token
        return request

    def test_token_hashed_at_rest(self):
        from django.test import RequestFactory

        response = HttpResponse()
        response = issue_trust(response, RequestFactory().post("/"), self.user)
        device = TrustedDevice.objects.get(user=self.user)
        self.assertEqual(len(device.token_hash), 64)
        self.assertNotIn(response.cookies[TRUST_COOKIE_NAME].value, device.token_hash)

    def test_device_label_parses_user_agents(self):
        self.assertEqual(
            device_label("Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"), "Chrome on Windows"
        )
        self.assertEqual(
            device_label("Mozilla/5.0 (Macintosh) Version/17.0 Safari/605.1"), "Safari on macOS"
        )
        self.assertEqual(
            device_label("Mozilla/5.0 (Linux; Android 13) Firefox/121.0"), "Firefox on Android"
        )
        self.assertEqual(device_label(""), "Browser on Unknown OS")

    # ------------------------------------------------------------- check_trust

    def test_check_trust_roundtrip(self):
        self.assertTrue(check_trust(self._trusted_request(), self.user))

    def test_check_trust_no_cookie(self):
        from django.test import RequestFactory

        self.assertFalse(check_trust(RequestFactory().get("/"), self.user))

    def test_check_trust_wrong_token(self):
        request = self._trusted_request()
        request.COOKIES[TRUST_COOKIE_NAME] = "0" * 64
        self.assertFalse(check_trust(request, self.user))

    def test_check_trust_other_user_rejected(self):
        other = User.objects.create_user(
            username="othertrust", password="CorrectPass123!", email="other@example.com"
        )
        request = self._trusted_request()
        self.assertFalse(check_trust(request, other))

    def test_check_trust_expired_rejected(self):
        from django.test import RequestFactory

        token = generate_token()
        TrustedDevice.objects.create(
            user=self.user,
            token_hash=hash_token(token),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        request = RequestFactory().get("/")
        request.COOKIES[TRUST_COOKIE_NAME] = token
        self.assertFalse(check_trust(request, self.user))

    # ------------------------------------------------------------- login flow

    def test_login_skips_challenge_on_trusted_browser(self):
        self.client.cookies[TRUST_COOKIE_NAME] = self._seed_device_token()
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, reverse("totp_challenge"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_requires_challenge_without_trust(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        self.assertEqual(response.url, reverse("totp_challenge"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_trust_cookie_cannot_skip_another_account(self):
        self.client.cookies[TRUST_COOKIE_NAME] = self._seed_device_token()
        other = User.objects.create_user(
            username="trustother", password="CorrectPass123!", email="to@example.com"
        )
        other.profile.email_verified = True
        other.profile.totp_secret = generate_secret()
        other.profile.totp_enabled = True
        other.profile.save(
            update_fields=["email_verified", "totp_secret", "totp_enabled"]
        )
        response = self.client.post(
            reverse("login"),
            {"username": other.username, "password": "CorrectPass123!"},
        )
        self.assertEqual(response.url, reverse("totp_challenge"))

    # ------------------------------------------------------------- issuance

    def test_challenge_with_trust_option_sets_cookie(self):
        self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        code = current_code(self.user.profile.totp_secret)
        response = self.client.post(
            reverse("totp_challenge"), {"code": code, "trust_device": "on"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(TRUST_COOKIE_NAME, response.cookies)
        # A fresh login on the same (now trusted) browser skips the challenge.
        self.client.post(reverse("logout"))
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        self.assertNotEqual(response.url, reverse("totp_challenge"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_challenge_without_trust_option_sets_no_cookie(self):
        self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        code = current_code(self.user.profile.totp_secret)
        response = self.client.post(reverse("totp_challenge"), {"code": code})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(TRUST_COOKIE_NAME, response.cookies)
        self.assertEqual(TrustedDevice.objects.filter(user=self.user).count(), 0)

    # ------------------------------------------------------------- revocation

    def test_revoke_device_forces_challenge_again(self):
        self.client.force_login(self.user)
        self._seed_device_token()
        device = TrustedDevice.objects.get(user=self.user)
        self.client.post(reverse("totp_trust_revoke", args=[device.pk]))
        self.assertEqual(TrustedDevice.objects.filter(user=self.user).count(), 0)
        self.client.logout()  # drop the force_login session so the login POST is real
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "CorrectPass123!"},
        )
        self.assertEqual(response.url, reverse("totp_challenge"))

    def test_cannot_revoke_another_users_device(self):
        self.client.force_login(self.user)
        other = User.objects.create_user(
            username="trustrevoke", password="CorrectPass123!", email="tr@example.com"
        )
        other_device = TrustedDevice.objects.create(
            user=other,
            token_hash=hash_token(generate_token()),
            expires_at=timezone.now() + timedelta(days=30),
        )
        response = self.client.post(
            reverse("totp_trust_revoke", args=[other_device.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(TrustedDevice.objects.filter(user=other).count(), 1)

    def test_revoke_all(self):
        self.client.force_login(self.user)
        self.client.cookies[TRUST_COOKIE_NAME] = self._seed_device_token()
        self.client.post(reverse("totp_trust_revoke_all"))
        self.assertEqual(TrustedDevice.objects.filter(user=self.user).count(), 0)

    def test_disable_2fa_wipes_devices(self):
        self.client.force_login(self.user)
        self.client.cookies[TRUST_COOKIE_NAME] = self._seed_device_token()
        self.client.post(reverse("totp_disable"), {"password": "CorrectPass123!"})
        self.assertEqual(TrustedDevice.objects.filter(user=self.user).count(), 0)

    def test_setup_page_lists_devices(self):
        self.client.cookies[TRUST_COOKIE_NAME] = self._seed_device_token()
        self.client.force_login(self.user)
        response = self.client.get(reverse("totp_setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trusted devices")
        self.assertContains(response, "Forget all devices")

    # ------------------------------------------------------------- helpers

    def _seed_device_token(self):
        """Create a trusted device for the test user and return its raw token."""
        token = generate_token()
        TrustedDevice.objects.create(
            user=self.user,
            token_hash=hash_token(token),
            user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/120.0",
            ip_address="127.0.0.1",
            last_used_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=30),
        )
        return token
