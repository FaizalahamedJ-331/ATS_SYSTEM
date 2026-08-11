"""Send a reminder email to accounts stuck unverified for too long.

Usage:

    python manage.py send_verification_reminders [--dry-run]

Finds active, non-superuser accounts whose email is still unverified and
whose signup is older than ``VERIFY_REMINDER_AFTER_HOURS`` (default 24h).
Each eligible account is emailed at most once per
``VERIFY_REMINDER_COOLDOWN_HOURS`` (default 24h) — the timestamp is stored
on the profile, so the command is safe to run from cron every hour.

Recommended schedule (e.g. system cron, Heroku Scheduler, GitHub Actions):

    0 * * * *  cd /path/to/app && venv/bin/python manage.py send_verification_reminders
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.email_utils import send_verification_reminder


class Command(BaseCommand):
    help = "Remind users whose email verification is still pending after a while."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List who would be emailed without sending anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()

        after = timedelta(hours=settings.VERIFY_REMINDER_AFTER_HOURS)
        cooldown = timedelta(hours=settings.VERIFY_REMINDER_COOLDOWN_HOURS)

        # Accounts that signed up long enough ago, are still active, not an
        # admin, and still unverified.
        users = (
            User.objects.filter(is_active=True)
            .exclude(is_superuser=True)
            .select_related("profile")
            .filter(
                profile__email_verified=False,
                date_joined__lt=now - after,
            )
            .exclude(profile__verification_reminder_sent_at__gte=now - cooldown)
            .order_by("date_joined")
        )

        sent = 0
        skipped = 0
        for user in users:
            # Belt-and-braces: superusers and verified accounts should never
            # get a reminder even if the queryset drifted.
            if user.profile.is_verified:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(f"[dry-run] would remind {user.email} ({user.get_username()})")
                sent += 1
                continue

            ok = send_verification_reminder(user)
            if ok:
                user.profile.verification_reminder_sent_at = now
                user.profile.save(update_fields=["verification_reminder_sent_at", "updated_at"])
                self.stdout.write(self.style.SUCCESS(f"reminded {user.email} ({user.get_username()})"))
                sent += 1
            else:
                # Delivery failed (e.g. SMTP down). Do NOT mark it as sent —
                # the next cron run will retry.
                self.stdout.write(self.style.WARNING(f"could not email {user.email} — will retry next run"))
                skipped += 1

        verb = "would remind" if dry_run else "reminded"
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {verb} {sent} account(s), skipped {skipped}."
            )
        )
