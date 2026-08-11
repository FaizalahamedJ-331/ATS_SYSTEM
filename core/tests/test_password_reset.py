"""Tests for the forgot-password / password-reset flow."""
import re

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(
    PASSWORD_RESET_RATE_LIMIT=100,
    PASSWORD_RESET_CONFIRM_RATE_LIMIT=100,
)
class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="forgotter",
            email="forgot@example.com",
            password="OldPass12345!",
        )

    def _request_reset(self, email="forgot@example.com"):
        return self.client.post(reverse("password_reset"), {"email": email})

    def _link_parts(self):
        match = re.search(
            r"/password-reset/confirm/([^/]+)/([^/\s]+)/", mail.outbox[0].body
        )
        return match.groups()

    def test_reset_form_page_renders(self):
        resp = self.client.get(reverse("password_reset"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reset your password")

    def test_request_sends_reset_email_with_absolute_link(self):
        resp = self._request_reset()
        self.assertRedirects(resp, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["forgot@example.com"])
        self.assertIn("Reset your TalentPulse password", email.subject)
        # The email carries an absolute, clickable link to the confirm view
        # (built from the request host, since the reset is web-initiated).
        match = re.search(
            r"http://testserver/password-reset/confirm/([^/]+)/([^/\s]+)/", email.body
        )
        self.assertIsNotNone(match, "reset link should be absolute and clickable")
        self.assertEqual(email.body.count("/password-reset/confirm/"), 1)

    def test_anti_enumeration_unknown_email(self):
        resp = self._request_reset(email="nobody@example.com")
        # Same redirect and same generic done page - no account leak.
        self.assertRedirects(resp, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset_round_trip(self):
        self._request_reset()
        uid, token = self._link_parts()

        # Opening the link scrubs the token from the URL (Django redirects
        # to an internal "set-password" URL) and renders the confirm form.
        url = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        resp = self.client.get(url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Choose a new password")
        confirm_url = resp.redirect_chain[-1][0] if resp.redirect_chain else url

        # Set a new password.
        resp = self.client.post(
            confirm_url,
            {"new_password1": "BrandNewPass456!", "new_password2": "BrandNewPass456!"},
        )
        self.assertRedirects(resp, reverse("password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPass456!"))
        self.assertFalse(self.user.check_password("OldPass12345!"))

    def test_confirm_link_is_single_use(self):
        self._request_reset()
        uid, token = self._link_parts()
        url = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        resp = self.client.get(url, follow=True)
        confirm_url = resp.redirect_chain[-1][0] if resp.redirect_chain else url
        # Set the new password using the scrubbed URL (the actual form).
        self.client.post(
            confirm_url,
            {"new_password1": "BrandNewPass456!", "new_password2": "BrandNewPass456!"},
        )
        # Re-using the original token now shows the invalid-link state.
        # (Assert on the form field, not the page title — both branches share
        # the "Choose a new password" <title>.)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Link invalid or expired")
        self.assertNotContains(resp, "id_new_password1")

    def test_garbage_token_shows_invalid_link(self):
        resp = self.client.get(
            reverse("password_reset_confirm", kwargs={"uidb64": "MQ", "token": "bad-token-123"})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Link invalid or expired")

    def test_expired_token_shows_invalid_link(self):
        # Build a token dated 10 days in the past so Django's timeout check
        # (default 3 days) fails, exactly as if the link sat too long.
        from datetime import datetime

        from django.contrib.auth.tokens import PasswordResetTokenGenerator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        generator = PasswordResetTokenGenerator()
        # Django's token timestamps count seconds since 2001-01-01 (naive
        # local time, matching the generator's own _now()).
        old_ts = int(generator._num_seconds(datetime.now())) - 10 * 86400
        token = generator._make_token_with_timestamp(
            self.user, old_ts, generator.secret
        )
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        resp = self.client.get(
            reverse("password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Link invalid or expired")

    def test_done_page_shows_generic_copy(self):
        self._request_reset()
        resp = self.client.get(reverse("password_reset_done"))
        self.assertContains(resp, "Check your inbox")

    def test_login_page_links_to_forgot_password(self):
        resp = self.client.get(reverse("login"))
        self.assertContains(resp, "Forgot your password?")
        self.assertContains(resp, reverse("password_reset"))


@override_settings(
    PASSWORD_RESET_RATE_LIMIT=2,
    PASSWORD_RESET_RATE_WINDOW=900,
    PASSWORD_RESET_CONFIRM_RATE_LIMIT=100,
)
class PasswordResetRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(
            username="rluser", email="rl@example.com", password="OldPass12345!"
        )

    def test_reset_request_limited_per_ip_and_email(self):
        url = reverse("password_reset")
        ok1 = self.client.post(url, {"email": "rl@example.com"})
        ok2 = self.client.post(url, {"email": "rl@example.com"})
        blocked = self.client.post(url, {"email": "rl@example.com"})
        self.assertEqual(ok1.status_code, 302)
        self.assertEqual(ok2.status_code, 302)
        self.assertEqual(blocked.status_code, 429)

    def test_reset_limit_is_per_address(self):
        url = reverse("password_reset")
        self.client.post(url, {"email": "rl@example.com"})
        self.client.post(url, {"email": "rl@example.com"})
        ok = self.client.post(url, {"email": "other@example.com"})
        self.assertEqual(ok.status_code, 302, "different address has its own bucket")
