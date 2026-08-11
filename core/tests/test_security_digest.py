"""Tests for the daily security-digest management command."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import SecurityLog


@override_settings(SECURITY_DIGEST_WINDOW_HOURS=24)
class SecurityDigestTests(TestCase):
    def setUp(self):
        mail.outbox = []
        self.user = User.objects.create_user(
            username="digestuser", password="CorrectPass123!", email="digest@example.com"
        )
        self.user.profile.email_verified = True
        self.user.profile.login_alerts_enabled = True
        self.user.profile.save(update_fields=["email_verified", "login_alerts_enabled"])

    def _event(self, event="login", hours_ago=0, detail="New browser"):
        entry = SecurityLog.objects.create(
            user=self.user, event=event, detail=detail, ip_address="127.0.0.1"
        )
        if hours_ago:
            # auto_now_add ignores a manual value on create, so backdate via
            # update() to simulate an older event.
            SecurityLog.objects.filter(pk=entry.pk).update(
                created_at=timezone.now() - timedelta(hours=hours_ago)
            )
        return entry

    def _run(self, **kwargs):
        return call_command("send_security_digests", **kwargs)

    # ------------------------------------------------------------- sending

    def test_sends_digest_with_events(self):
        self._event("login")
        self._event("device_trusted", detail="Chrome on Windows")
        self._run()
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("Your daily TalentPulse security digest", msg.subject)
        self.assertIn("Signed in", msg.body)
        self.assertIn("Browser trusted for 30 days", msg.body)
        self.assertIn("127.0.0.1", msg.body)
        # Grouped summary present.
        self.assertIn("Sign-ins: 1", msg.body)
        self.assertIn("Devices: 1", msg.body)
        # sent_at recorded so the next run won't double-send.
        self.user.profile.refresh_from_db()
        self.assertIsNotNone(self.user.profile.security_digest_sent_at)

    def test_no_email_without_events(self):
        self._run()
        self.assertEqual(len(mail.outbox), 0)
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.security_digest_sent_at)

    def test_no_email_when_not_opted_in(self):
        self.user.profile.login_alerts_enabled = False
        self.user.profile.save(update_fields=["login_alerts_enabled"])
        self._event("login")
        self._run()
        self.assertEqual(len(mail.outbox), 0)

    def test_only_window_events_included(self):
        self._event("login", hours_ago=25)  # older than the 24h window
        self._run()
        self.assertEqual(len(mail.outbox), 0)

    def test_dedup_within_window(self):
        self._event("login")
        self._run()
        self.assertEqual(len(mail.outbox), 1)
        self._event("2fa_enabled")
        self._run()  # within the window -> skipped
        self.assertEqual(len(mail.outbox), 1)

    def test_sends_again_after_window(self):
        self._event("login")
        self._run()
        # Pretend the last digest was sent 25h ago.
        self.user.profile.security_digest_sent_at = timezone.now() - timedelta(hours=25)
        self.user.profile.save(update_fields=["security_digest_sent_at"])
        self._event("password_changed", detail="turned on")
        self._run()
        self.assertEqual(len(mail.outbox), 2)

    def test_dry_run_sends_nothing(self):
        self._event("login")
        self._run(dry_run=True)
        self.assertEqual(len(mail.outbox), 0)
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.security_digest_sent_at)

    def test_inactive_user_skipped(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self._event("login")
        self._run()
        self.assertEqual(len(mail.outbox), 0)

    def test_more_than_20_events_capped(self):
        for i in range(25):
            self._event("login", detail=f"event {i}")
        self._run()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("5 more events", mail.outbox[0].body)
        # Newest events shown (event 24 is the newest).
        self.assertIn("event 24", mail.outbox[0].body)
        self.assertNotIn("event 0", mail.outbox[0].body)

    def test_delivery_failure_does_not_mark_sent(self):
        """A failed send leaves sent_at untouched so the next run retries."""
        from unittest import mock

        self._event("login")
        with mock.patch(
            "core.management.commands.send_security_digests.send_security_digest",
            return_value=False,
        ):
            self._run()
        self.assertEqual(len(mail.outbox), 0)
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.security_digest_sent_at)
