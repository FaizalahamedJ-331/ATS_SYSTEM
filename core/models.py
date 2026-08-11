from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class BaseModel(models.Model):
    """Abstract base with created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserProfile(models.Model):
    """Per-user state that sits next to Django's built-in auth User.

    Holds the email-verification flag used by the signup flow: new accounts
    must verify their email before their first login (the signed link arrives
    in the welcome email). Superusers are always treated as verified.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    email_verified = models.BooleanField(default=False)

    # Two-factor authentication (TOTP, authenticator apps like Google
    # Authenticator / Authy / 1Password). totp_secret is the base32 secret;
    # totp_enabled is the master switch. When enabled, login requires a
    # 6-digit code from the app after the password. null = never set up.
    totp_secret = models.CharField(max_length=64, null=True, blank=True)
    totp_enabled = models.BooleanField(default=False)
    totp_verified_at = models.DateTimeField(null=True, blank=True)

    # One-time recovery codes (for when the authenticator app is lost).
    # Stored as salted PBKDF2 hashes, never plaintext: JSON list of hashes,
    # each usable exactly once. Empty = no codes issued.
    recovery_codes = models.JSONField(default=list, blank=True)
    recovery_codes_generated_at = models.DateTimeField(null=True, blank=True)

    # Last time a verification reminder email was sent (null = never). Used by
    # the `send_verification_reminders` management command so stale accounts
    # are nudged at most once per cooldown window instead of every cron run.
    verification_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    # "Notify me of new logins" — when ON, a successful sign-in from a browser
    # that isn't trusted (no valid "remember this device" cookie) emails the
    # user with the device, IP and time, so a stolen password is spotted fast.
    # Also gates the daily security digest (``send_security_digests``).
    login_alerts_enabled = models.BooleanField(default=False)

    # When the daily security digest was last emailed (null = never). Written
    # by the ``send_security_digests`` management command so repeated cron
    # runs never double-send within the digest window.
    security_digest_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_username()} (verified={self.email_verified})"

    @property
    def is_verified(self):
        """Superusers bypass verification (they are created by an admin)."""
        return self.user.is_superuser or self.email_verified


class TrustedDevice(models.Model):
    """A browser the user opted to trust for a while, skipping the 2FA
    challenge on that device.

    The cookie handed to the browser contains a random 256-bit token; only
    its SHA-256 digest is stored here, so a database leak never yields a
    usable trust token. Each row belongs to exactly one user, so a cookie
    can't be replayed across accounts.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trusted_devices")
    token_hash = models.CharField(max_length=64, db_index=True)  # sha256 hex of the cookie token
    user_agent = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Trusted device #{self.pk} for {self.user_id}"


class SecurityLog(models.Model):
    """A per-user security audit trail: 2FA changes, trusted-device events,
    recovery-code issuance, password changes and sign-ins.

    The event code drives the UI label/icon (see ``core/security_log.py``);
    ``detail`` carries context like the friendly device label. Rows are
    capped per user (oldest pruned) so the table can't grow forever.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="security_log")
    event = models.CharField(max_length=40, db_index=True)
    detail = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["user", "-created_at"], name="sec_log_user_created")]

    def __str__(self):
        return f"{self.event} @ {self.created_at:%Y-%m-%d %H:%M} for user {self.user_id}"


@receiver(post_save, sender=User)
def _ensure_user_profile(sender, instance, created, **kwargs):
    """Every User automatically gets a profile; superusers start verified."""
    if created:
        UserProfile.objects.create(user=instance, email_verified=instance.is_superuser)
    else:
        # Keep a fresh install consistent even if a profile was somehow missing.
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={"email_verified": instance.is_superuser},
        )
