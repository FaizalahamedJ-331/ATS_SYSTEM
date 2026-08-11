"""Tests for one-time 2FA recovery codes."""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.totp import (
    current_code,
    generate_recovery_codes,
    hash_recovery_codes,
    normalize_recovery_code,
    verify_recovery_code,
)


@override_settings(TOTP_CHALLENGE_RATE_LIMIT=100, TOTP_CHALLENGE_RATE_WINDOW=900)
class RecoveryCodeHelperTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="recovery", password="CorrectPass123!", email="rc@example.com"
        )
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])

    def test_generate_and_normalize(self):
        codes = generate_recovery_codes()
        self.assertEqual(len(codes), 8)
        self.assertEqual(len(codes[0]), 11)  # XXXXX-XXXXX
        self.assertEqual(normalize_recovery_code("ab12c-de34f"), "AB12CDE34F")
        self.assertEqual(normalize_recovery_code("  ab12cde34f  "), "AB12CDE34F")

    def test_verify_consumes_once(self):
        plain = generate_recovery_codes(3)
        profile = self.user.profile
        profile.recovery_codes = hash_recovery_codes(plain)
        profile.save()

        self.assertTrue(verify_recovery_code(profile, plain[1].lower()))  # case-insensitive
        profile.refresh_from_db()
        self.assertEqual(len(profile.recovery_codes), 2)
        # Reusing the same code is rejected.
        self.assertFalse(verify_recovery_code(profile, plain[1]))
        # An unused code still works.
        self.assertTrue(verify_recovery_code(profile, plain[0]))
        profile.refresh_from_db()
        self.assertEqual(len(profile.recovery_codes), 1)

    def test_wrong_code_does_not_mutate(self):
        plain = generate_recovery_codes(2)
        profile = self.user.profile
        profile.recovery_codes = hash_recovery_codes(plain)
        profile.save()
        self.assertFalse(verify_recovery_code(profile, "XXXXX-XXXXX"))
        profile.refresh_from_db()
        self.assertEqual(len(profile.recovery_codes), 2)

    def test_codes_stored_hashed_not_plaintext(self):
        plain = generate_recovery_codes(2)
        profile = self.user.profile
        profile.recovery_codes = hash_recovery_codes(plain)
        profile.save()
        profile.refresh_from_db()
        for stored in profile.recovery_codes:
            self.assertTrue(stored.startswith("pbkdf2_sha256$"))
            self.assertNotIn(plain[0][:8], stored)


class RecoveryCodeFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="rcflow", password="CorrectPass123!", email="rcf@example.com"
        )
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])

    def _enable_2fa(self):
        """Full enable: GET setup (secret), POST correct TOTP -> recovery page."""
        self.client.force_login(self.user)
        self.client.get(reverse("totp_setup"))
        secret = self.client.session.get("totp_setup_secret")
        resp = self.client.post(reverse("totp_setup"), {"code": current_code(secret)})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("totp_recovery_codes"))
        # The show-once page displays the 8 plaintext codes. (Don't use
        # assertRedirects - its fetch would consume the one-shot session.)
        resp = self.client.get(reverse("totp_recovery_codes"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "shown only once")
        self.assertContains(resp, "-")  # XXXXX-XXXXX codes visible
        return [c for c in resp.context["codes"]]

    def test_recovery_code_unlocks_login(self):
        codes = self._enable_2fa()
        self.client.logout()

        # Password login -> challenge.
        resp = self.client.post(
            reverse("login"), {"username": "rcflow", "password": "CorrectPass123!"}
        )
        self.assertRedirects(resp, reverse("totp_challenge"))

        # A recovery code signs you in (no TOTP needed).
        resp = self.client.post(reverse("totp_challenge"), {"code": codes[2].lower()})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(int(self.client.session.get("_auth_user_id")), self.user.pk)
        # And it was consumed.
        self.user.profile.refresh_from_db()
        self.assertEqual(len(self.user.profile.recovery_codes), 7)

    def test_recovery_code_is_single_use(self):
        codes = self._enable_2fa()
        self.client.logout()
        self.client.post(
            reverse("login"), {"username": "rcflow", "password": "CorrectPass123!"}
        )
        self.client.post(reverse("totp_challenge"), {"code": codes[0]})
        # Second use of the same code fails.
        self.client.logout()
        self.client.post(
            reverse("login"), {"username": "rcflow", "password": "CorrectPass123!"}
        )
        resp = self.client.post(reverse("totp_challenge"), {"code": codes[0]})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "isn&#x27;t valid")
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_regenerate_requires_password_and_invalidates_old(self):
        codes = self._enable_2fa()
        self.user.profile.refresh_from_db()
        old_hash = self.user.profile.recovery_codes[0]

        # Wrong password -> unchanged.
        resp = self.client.post(
            reverse("totp_recovery_codes_regenerate"), {"password": "nope"}
        )
        self.assertRedirects(resp, reverse("totp_setup"))
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.recovery_codes[0], old_hash)

        # Correct password -> fresh batch, old codes invalidated.
        resp = self.client.post(
            reverse("totp_recovery_codes_regenerate"), {"password": "CorrectPass123!"}
        )
        self.assertRedirects(resp, reverse("totp_recovery_codes"))
        self.user.profile.refresh_from_db()
        self.assertNotEqual(self.user.profile.recovery_codes[0], old_hash)
        # The old plaintext code no longer works.
        self.client.logout()
        self.client.post(
            reverse("login"), {"username": "rcflow", "password": "CorrectPass123!"}
        )
        resp = self.client.post(reverse("totp_challenge"), {"code": codes[0]})
        self.assertContains(resp, "isn&#x27;t valid")

    def test_show_once_then_remaining_count(self):
        self._enable_2fa()
        # Second visit: no codes shown, just the remaining count + regenerate.
        resp = self.client.get(reverse("totp_recovery_codes"))
        self.assertContains(resp, "left")
        self.assertContains(resp, "Generate new codes")
        self.assertNotContains(resp, "shown only once")
