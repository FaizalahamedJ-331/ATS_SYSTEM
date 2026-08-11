"""Email opted-in users a daily summary of their security-log events.

Usage:

    python manage.py send_security_digests [--dry-run]

Every active user with sign-in alerts ON gets one digest per
``SECURITY_DIGEST_WINDOW_HOURS`` (default 24h) summarizing their security
events (sign-ins, 2FA changes, trusted-device activity) since the last
digest - or the last window when none was sent yet. Users with nothing to
report get no email, and ``security_digest_sent_at`` (stored per user) makes
repeated cron runs safe - no double-sends within the window.

Recommended schedule (system cron, Heroku Scheduler, GitHub Actions):

    30 8 * * *  cd /path/to/app && venv/bin/python manage.py send_security_digests
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.email_utils import send_security_digest


class Command(BaseCommand):
    help = "Email each opted-in user a daily security digest."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List who would be emailed without sending anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()
        window = timedelta(hours=settings.SECURITY_DIGEST_WINDOW_HOURS)
        period = f"in the last {settings.SECURITY_DIGEST_WINDOW_HOURS} hours"

        # Opted-in, active users (with an email to mail to) who haven't been
        # emailed within the window. NOTE: the stale-sent_at check and the
        # sent_at write below aren't atomic, so two overlapping cron runs can
        # briefly double-send - acceptable for an ATS; a lock or conditional
        # update would make it strict.
        users = (
            User.objects.filter(is_active=True, profile__login_alerts_enabled=True)
            .exclude(email="")
            .select_related("profile")
            .filter(
                Q(profile__security_digest_sent_at__isnull=True)
                | Q(profile__security_digest_sent_at__lt=now - window)
            )
            .order_by("username")
        )

        sent = 0
        skipped = 0
        for user in users:
            since = user.profile.security_digest_sent_at or (now - window)
            # The email's "period" copy must match what it actually covers:
            # since the last digest (which can be days ago) vs the default
            # window when no digest was ever sent.
            if user.profile.security_digest_sent_at:
                period = f"since {user.profile.security_digest_sent_at.strftime('%b %d')}"
            else:
                period = f"in the last {settings.SECURITY_DIGEST_WINDOW_HOURS} hours"
            events = user.security_log.filter(created_at__gte=since)
            if not events.exists():
                # Nothing happened - no email beats a boring email.
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"[dry-run] would send digest to {user.email} ({user.get_username()}) "
                    f"- {events.count()} event(s)"
                )
                sent += 1
                continue

            ok = send_security_digest(user, events, period=period)
            if ok:
                user.profile.security_digest_sent_at = now
                user.profile.save(update_fields=["security_digest_sent_at", "updated_at"])
                self.stdout.write(
                    self.style.SUCCESS(f"digest sent to {user.email} ({user.get_username()})")
                )
                sent += 1
            else:
                # Delivery failed (SMTP down etc.). Don't mark as sent - the
                # next run retries.
                self.stdout.write(
                    self.style.WARNING(f"could not email {user.email} - will retry next run")
                )
                skipped += 1

        verb = "would send" if dry_run else "sent"
        self.stdout.write(
            self.style.SUCCESS(f"Done. {verb} {sent} digest(s), skipped {skipped}.")
        )
