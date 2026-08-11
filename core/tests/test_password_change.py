"""Tests for the authenticated change-password (Settings) page."""
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="changer",
            email="changer@example.com",
            password="OldPass12345!",
        )
        self.url = reverse("password_change")

    def _login(self):
        self.client.force_login(self.user)

    def _change(self, old="OldPass12345!", new="BrandNewPass456!", confirm="BrandNewPass456!"):
        return self.client.post(
            self.url,
            {"old_password": old, "new_password1": new, "new_password2": confirm},
        )

    def test_requires_authentication(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.url)

    def test_page_renders_for_authenticated_user(self):
        self._login()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Change password")
        self.assertContains(resp, "id_old_password")
        self.assertContains(resp, "id_new_password1")
        # The strength meter is wired in (hashed by ManifestStaticFilesStorage).
        self.assertContains(resp, "password-meter")
        self.assertContains(resp, "data-pw-meter")

    def test_wrong_old_password_rejected(self):
        self._login()
        resp = self._change(old="WrongOld999!")
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors
        self.assertContains(resp, "incorrect")  # "Your old password was entered incorrectly…"
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass12345!"))

    def test_weak_new_password_rejected(self):
        self._login()
        resp = self._change(new="aaaaaaaa", confirm="aaaaaaaa")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "field-error")  # inline error shown
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass12345!"))

    def test_mismatched_confirmation_rejected(self):
        self._login()
        resp = self._change(new="BrandNewPass456!", confirm="DifferentPass789!")
        self.assertEqual(resp.status_code, 200)
        # Django's mismatch error is on the confirm field (HTML-escaped).
        self.assertContains(resp, "didn", html=False)
        self.assertContains(resp, "match", html=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass12345!"))

    def test_valid_change_updates_password_and_shows_success(self):
        self._login()
        resp = self._change()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPass456!"))
        self.assertFalse(self.user.check_password("OldPass12345!"))
        # Success toast message is queued and rendered on the next page load.
        # (We GET the redirect target ourselves — assertRedirects would consume
        # the one-shot message first.)
        resp = self.client.get(self.url)
        self.assertContains(resp, "password has been changed")
        self.assertContains(resp, "django-messages")
