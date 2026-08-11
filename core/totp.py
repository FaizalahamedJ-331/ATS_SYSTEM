"""TOTP two-factor helpers (RFC 6238) built on pyotp.

Secrets are stored per-user in UserProfile.totp_secret (base32). Codes are
verified with a 1-step drift window, and the last successfully used code is
cached per secret for the code's lifetime so replaying the same code is
rejected (standard TOTP replay protection).
"""

import base64
import hashlib
import time

import pyotp
from django.conf import settings
from django.core.cache import cache


STEP = 30  # TOTP time step in seconds
WINDOW = 1  # allow +/- 1 step of clock drift


def generate_secret():
    """Return a fresh random base32 secret for a new authenticator app."""
    return pyotp.random_base32()


def otpauth_uri(secret, user):
    """The otpauth:// URI an authenticator app scans from the QR code."""
    issuer = getattr(settings, "TOTP_ISSUER", "TalentPulse ATS")
    label = (user.get_username() or "user").strip()
    return pyotp.TOTP(secret).provisioning_uri(name=label, issuer_name=issuer)


def qr_svg(secret, user):
    """Render the provisioning URI as an inline SVG data URL (no image libs).

    SVG keeps the QR dependency-free: a tiny QR encoder produces the matrix
    and we draw it as rects. Suitable for the setup page without Pillow.
    """
    try:
        from core.qr import qr_matrix, matrix_to_svg_data_uri
        return matrix_to_svg_data_uri(qr_matrix(otpauth_uri(secret, user)), size=5)
    except Exception:
        return ""


def _replay_key(secret):
    return f"totp:last:{hashlib.sha256(secret.encode()).hexdigest()}"


def verify_code(secret, code, user=None):
    """Return True if ``code`` is a valid TOTP for ``secret``.

    Enforces replay protection at the *time-step* level: TOTP accepts the
    code for the current step plus ``WINDOW`` step of clock drift, so we
    record which step the code belongs to and reject any later attempt that
    produces the same code - including a replay while the code is still
    within its validity window. ``cache.add`` is atomic (first writer wins),
    so two concurrent identical codes can't both pass on a shared cache.
    """
    if not secret or not code:
        return False
    code = str(code).strip()
    if not (code.isdigit() and len(code) == 6):
        return False
    totp = pyotp.TOTP(secret, interval=STEP)
    now = int(time.time())
    if not totp.verify(code, for_time=now, valid_window=WINDOW):
        return False
    # Replay protection: a valid code is accepted once per time step. Compute
    # the step counter the same way pyotp does (local time, like .now()/.at())
    # and record it; a repeat of the same code - even while still within its
    # validity window - is rejected. cache.add is atomic, so two concurrent
    # identical codes can't both pass on a shared cache.
    counter = int(time.mktime(time.localtime(now)) // STEP)
    used = cache.get(_replay_key(secret)) or set()
    if counter in used:
        return False
    if not cache.add(_replay_key(secret), used | {counter}, STEP * (WINDOW + 1)):
        return False
    return True


def current_code(secret):
    """Return the code valid right now (used by tests and the demo setup)."""
    return pyotp.TOTP(secret, interval=STEP).now()


# ---------------------------------------------------------------------------
# One-time recovery codes (for lost authenticator apps)
# ---------------------------------------------------------------------------
# A small batch of single-use codes is issued when 2FA is enabled. They are
# stored as salted PBKDF2 hashes (like passwords), never plaintext, and each
# can be redeemed exactly once - either at the 2FA challenge or anywhere a
# TOTP code is expected.

from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.utils.crypto import get_random_string
from secrets import token_hex

RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_BYTES = 5  # 10 hex chars, grouped 5-5 for readability


def _recovery_hasher():
    return PBKDF2PasswordHasher()


def generate_recovery_codes(count=RECOVERY_CODE_COUNT):
    """Return a fresh list of plaintext recovery codes (shown once to the user)."""
    codes = []
    for _ in range(count):
        raw = token_hex(RECOVERY_CODE_BYTES).upper()
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_recovery_codes(plain_codes):
    """Hash a list of plaintext codes for storage (salted, per-code salt).

    Codes are normalized (dashes stripped, upper-cased) first so the stored
    hash matches what ``verify_recovery_code`` compares against.
    """
    return [
        _recovery_hasher().encode(normalize_recovery_code(c), salt=get_random_string(12))
        for c in plain_codes
    ]


def normalize_recovery_code(code):
    """Trim and strip separators so 'ABCDE-FGHIJ' == 'abcdefghij'."""
    return (code or "").strip().upper().replace("-", "").replace(" ", "")


def verify_recovery_code(profile, code):
    """Consume ``code`` from ``profile.recovery_codes`` if valid.

    Returns True when the code matches an unused hash, in which case that
    hash is removed (single use). Comparison is constant-time via Django's
    hasher. Invalid codes never mutate the stored list.
    """
    normalized = normalize_recovery_code(code)
    if not normalized:
        return False
    hashes = list(profile.recovery_codes or [])
    for i, stored in enumerate(hashes):
        if _recovery_hasher().verify(normalized, stored):
            hashes.pop(i)
            profile.recovery_codes = hashes
            profile.save(update_fields=["recovery_codes", "updated_at"])
            return True
    return False
