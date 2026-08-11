"""Tests for the `send_verification_reminders` management command."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import UserProfile


@override_settings(VERIFY_REMINDER_AFTER_HOURS=24, VERIFY_REMINDER_COOLDOWN_HOURS=24)
class VerificationReminderCommandTests(TestCase):
    def _pending_user(self, username, email, age_hours=48, verified=False, active=True, superuser=False):
        """Create a user with a profile aged `age_hours` ago."""
        user = User.objects.create_user(
            username=username, email=email, password="pw12345678x", is_active=active
        )
        user.is_superuser = superuser
        user.is_staff = superuser
        user.date_joined = timezone.now() - timedelta(hours=age_hours)
        user.save(update_fields=["is_superuser", "is_staff", "date_joined"])
        user.refresh_from_db()
        profile = UserProfile.objects.get(user=user)
        profile.email_verified = verified
        profile.save(update_fields=["email_verified"])
        return user

    def test_reminds_stale_unverified_accounts(self):
        stale = self._pending_user("stale", "stale@example.com", age_hours=48)
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [stale.email])
        self.assertIn("Still waiting", mail.outbox[0].subject)
        self.assertIn("verify", mail.outbox[0].body.lower())
        # The reminder link is a fresh verification link.
        stale.refresh_from_db()
        self.assertIsNotNone(stale.profile.verification_reminder_sent_at)

    def test_skips_recent_accounts(self):
        self._pending_user("fresh", "fresh@example.com", age_hours=2)
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 0)

    def test_skips_verified_superuser_and_inactive(self):
        self._pending_user("verif", "verif@example.com", age_hours=48, verified=True)
        self._pending_user("admin", "admin@example.com", age_hours=48, superuser=True)
        self._pending_user("gone", "gone@example.com", age_hours=48, active=False)
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 0)

    def test_cooldown_prevents_spam(self):
        self._pending_user("nagged", "nagged@example.com", age_hours=48)
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 1)
        # Immediately re-run: within the cooldown, no second email.
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 1)

    def test_reminds_again_after_cooldown(self):
        user = self._pending_user("again", "again@example.com", age_hours=48)
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 1)
        # Pretend the cooldown elapsed.
        user.refresh_from_db()
        user.profile.verification_reminder_sent_at = timezone.now() - timedelta(hours=25)
        user.profile.save(update_fields=["verification_reminder_sent_at"])
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 2)

    def test_dry_run_sends_nothing(self):
        self._pending_user("peek", "peek@example.com", age_hours=48)
        call_command("send_verification_reminders", dry_run=True, verbosity=0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(SITE_URL="https://ats.example.com")
    def test_reminder_link_is_absolute_via_site_url(self):
        # Cron runs have no request, so the link must use SITE_URL or the
        # email is unclickable.
        self._pending_user("cron", "cron@example.com", age_hours=48)
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://ats.example.com/verify-email/", mail.outbox[0].body)

    def test_boundary_exactly_after_threshold(self):
        # A touch UNDER the threshold is not yet overdue (strictly older than
        # is required; a few seconds of slack keeps the test deterministic).
        self._pending_user(
            "edge", "edge@example.com",
            age_hours=24 - 1 / 60,  # 23h59m
        )
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 0)
        # One hour past the threshold is overdue.
        self._pending_user("edge2", "edge2@example.com", age_hours=25)
        call_command("send_verification_reminders", verbosity=0)
        self.assertEqual(len(mail.outbox), 1)
