"""Tests for TOTP two-factor authentication (setup, challenge, disable)."""
import re

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.totp import current_code, generate_secret


@override_settings(TOTP_CHALLENGE_RATE_LIMIT=3, TOTP_CHALLENGE_RATE_WINDOW=900)
class TotpSetupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="totpuser", password="CorrectPass123!", email="t@example.com"
        )
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])

    def _login(self):
        self.client.force_login(self.user)

    def test_setup_page_shows_qr_and_secret(self):
        self._login()
        resp = self.client.get(reverse("totp_setup"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data:image/svg+xml;base64,")
        self.assertContains(resp, "Manual setup secret")

    def test_enable_requires_valid_code(self):
        self._login()
        # Establishing the setup page generates the secret in the session.
        self.client.get(reverse("totp_setup"))
        secret = self.client.session.get("totp_setup_secret")
        self.assertTrue(secret)

        # Wrong code -> not enabled.
        resp = self.client.post(reverse("totp_setup"), {"code": "000000"})
        self.assertEqual(resp.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.totp_enabled)

        # Correct code -> enabled, secret persisted, recovery codes issued.
        resp = self.client.post(reverse("totp_setup"), {"code": current_code(secret)})
        self.assertRedirects(resp, reverse("totp_recovery_codes"))
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.totp_enabled)
        self.assertEqual(self.user.profile.totp_secret, secret)
        # Recovery codes are stored hashed (never plaintext) and 8 were issued.
        self.assertEqual(len(self.user.profile.recovery_codes), 8)
        self.assertNotIn("-", self.user.profile.recovery_codes[0])

    def test_requires_authentication(self):
        resp = self.client.get(reverse("totp_setup"))
        self.assertEqual(resp.status_code, 302)

    def test_disable_requires_password(self):
        self._login()
        secret = generate_secret()
        self.user.profile.totp_secret = secret
        self.user.profile.totp_enabled = True
        self.user.profile.save()

        # Wrong password -> still enabled, redirected back with an error toast.
        resp = self.client.post(reverse("totp_disable"), {"password": "nope"})
        self.assertRedirects(resp, reverse("totp_setup"))
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.totp_enabled)

        # Correct password -> disabled (recovery codes wiped too).
        self.user.profile.recovery_codes = ["pbkdf2_sha256$x"]
        self.user.profile.save()
        resp = self.client.post(reverse("totp_disable"), {"password": "CorrectPass123!"})
        self.assertRedirects(resp, reverse("password_change"))
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.totp_enabled)
        self.assertIsNone(self.user.profile.totp_secret)
        self.assertEqual(self.user.profile.recovery_codes, [])


@override_settings(TOTP_CHALLENGE_RATE_LIMIT=3, TOTP_CHALLENGE_RATE_WINDOW=900)
class TotpChallengeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.secret = generate_secret()
        self.user = User.objects.create_user(
            username="challenged", password="CorrectPass123!", email="c@example.com"
        )
        self.user.profile.email_verified = True
        self.user.profile.totp_secret = self.secret
        self.user.profile.totp_enabled = True
        self.user.profile.save()

    def _password_login(self):
        return self.client.post(
            reverse("login"),
            {"username": "challenged", "password": "CorrectPass123!"},
        )

    def test_password_login_redirects_to_challenge(self):
        resp = self._password_login()
        self.assertRedirects(resp, reverse("totp_challenge"))
        # Not signed in yet.
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_correct_code_signs_in(self):
        self._password_login()
        resp = self.client.post(reverse("totp_challenge"), {"code": current_code(self.secret)})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.user.pk)

    def test_wrong_code_rejected(self):
        self._password_login()
        resp = self.client.post(reverse("totp_challenge"), {"code": "123456"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "isn&#x27;t valid")
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_replay_protection(self):
        """The same code can't be used twice within its window."""
        self._password_login()
        code = current_code(self.secret)
        resp = self.client.post(reverse("totp_challenge"), {"code": code})
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.user.pk)
        # Log out, log in again, replay the same code -> rejected.
        self.client.logout()
        self._password_login()
        resp = self.client.post(reverse("totp_challenge"), {"code": code})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "isn&#x27;t valid")

    def test_challenge_rate_limited(self):
        self._password_login()
        for _ in range(3):
            self.client.post(reverse("totp_challenge"), {"code": "999999"})
        resp = self.client.post(reverse("totp_challenge"), {"code": current_code(self.secret)})
        self.assertEqual(resp.status_code, 429)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_challenge_without_pending_login_redirects(self):
        resp = self.client.get(reverse("totp_challenge"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("login"))

    def test_user_without_2fa_logs_in_directly(self):
        plain = User.objects.create_user(
            username="plainuser", password="CorrectPass123!", email="p@example.com"
        )
        plain.profile.email_verified = True
        plain.profile.save(update_fields=["email_verified"])
        resp = self.client.post(
            reverse("login"),
            {"username": "plainuser", "password": "CorrectPass123!"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertNotEqual(resp.url, reverse("totp_challenge"))
        self.assertEqual(int(self.client.session.get("_auth_user_id")), plain.pk)

    def test_qr_decodes_to_otpauth_uri(self):
        """The QR matrix must actually encode the provisioning URI (segno ref)."""
        import segno
        from core.totp import otpauth_uri
        from core.qr import qr_matrix

        uri = otpauth_uri(self.secret, self.user)
        ref = segno.make(uri, error="m")
        ours = qr_matrix(uri)
        n = ref.version * 4 + 17
        diff = sum(
            1
            for r in range(n)
            for c in range(n)
            if bool(ours[r][c]) != bool(ref.matrix[r][c])
        )
        self.assertEqual(diff, 0)
