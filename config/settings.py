"""
Django settings for the ATS Screening System.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    val = os.environ.get(name)
    if val is None or not val.strip().isdigit():
        return default
    return int(val.strip())


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-ats-screening-dev-key-change-me-in-production",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

# Canonical site URL, e.g. https://ats.example.com. Used to build absolute
# links inside emails sent outside a request context (e.g. the verification
# reminder cron command). When empty, request-less emails fall back to a
# relative link (fine for the dev console backend).
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "core",
    "jobs",
    "candidates",
    "screening",
    "interviews",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.debug",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.public_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database — SQLite by default; set DB_ENGINE=postgres for production
# ---------------------------------------------------------------------------
def _db_config():
    if os.environ.get("DB_ENGINE", "sqlite").lower() == "postgres":
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "ats"),
            "USER": os.environ.get("DB_USER", "ats"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / os.environ.get("DB_NAME", "db.sqlite3"),
    }


DATABASES = {"default": _db_config()}

# Trust proxy headers (set HTTPS correctly behind Nginx / PaaS load balancers)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# Production hardening — enable these in .env when serving over HTTPS
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0") or 0)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
# Strong-password policy: stock validators plus a character-diversity rule
# (must mix >= 3 of lowercase / uppercase / digits / symbols). The minimum
# length is 10 by default; the client-side strength meter mirrors these rules
# via the PUBLIC PASSWORD_MIN_LENGTH setting below.
PASSWORD_MIN_LENGTH = env_int("PASSWORD_MIN_LENGTH", 10)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": PASSWORD_MIN_LENGTH},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {
        "NAME": "core.validators.CharacterDiversityValidator",
        "OPTIONS": {"min_classes": 3},
    },
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise serves collected static files in production
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Email — console backend by default (dev prints to the terminal, so the
# verification link is visible without configuring SMTP). Override in .env
# for production (e.g. EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# plus EMAIL_HOST / EMAIL_PORT / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD).
# ---------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "TalentPulse <no-reply@talentpulse.local>")

# ---------------------------------------------------------------------------
# Rate limiting — protects the public auth endpoints from abuse (signup
# spam, verification-email flooding). Sliding window per client. Defaults are
# generous for real users; override in .env when you know your traffic.
# ---------------------------------------------------------------------------
SIGNUP_RATE_LIMIT = env_int("SIGNUP_RATE_LIMIT", 5)          # accounts per IP
SIGNUP_RATE_WINDOW = env_int("SIGNUP_RATE_WINDOW", 3600)     # ...per hour
RESEND_RATE_LIMIT = env_int("RESEND_RATE_LIMIT", 3)          # emails per IP+address
RESEND_RATE_WINDOW = env_int("RESEND_RATE_WINDOW", 900)      # ...per 15 minutes
LOGIN_RATE_LIMIT = env_int("LOGIN_RATE_LIMIT", 5)            # failed logins per IP+username
LOGIN_IP_RATE_LIMIT = env_int("LOGIN_IP_RATE_LIMIT", 20)     # failed logins per IP (spraying)
LOGIN_RATE_WINDOW = env_int("LOGIN_RATE_WINDOW", 900)        # ...per 15 minutes
ACCOUNT_LOCKOUT_LIMIT = env_int("ACCOUNT_LOCKOUT_LIMIT", 10)  # failed logins per username (all IPs)
ACCOUNT_LOCKOUT_WINDOW = env_int("ACCOUNT_LOCKOUT_WINDOW", 900)  # ...per 15 minutes
ACCOUNT_LOCKOUT_COOLDOWN = env_int("ACCOUNT_LOCKOUT_COOLDOWN", 900)  # account locked for 15 minutes
PASSWORD_RESET_RATE_LIMIT = env_int("PASSWORD_RESET_RATE_LIMIT", 3)   # emails per IP+address
PASSWORD_RESET_RATE_WINDOW = env_int("PASSWORD_RESET_RATE_WINDOW", 900)  # ...per 15 minutes
PASSWORD_RESET_CONFIRM_RATE_LIMIT = env_int("PASSWORD_RESET_CONFIRM_RATE_LIMIT", 10)  # new-password POSTs
PASSWORD_RESET_CONFIRM_RATE_WINDOW = env_int("PASSWORD_RESET_CONFIRM_RATE_WINDOW", 3600)  # ...per hour

# ---------------------------------------------------------------------------
# Two-factor authentication (TOTP authenticator apps)
# ---------------------------------------------------------------------------
TOTP_ISSUER = os.environ.get("TOTP_ISSUER", "TalentPulse ATS")
TOTP_CHALLENGE_RATE_LIMIT = env_int("TOTP_CHALLENGE_RATE_LIMIT", 5)   # wrong codes per challenge
TOTP_CHALLENGE_RATE_WINDOW = env_int("TOTP_CHALLENGE_RATE_WINDOW", 900)  # ...per 15 minutes
# "Remember this device" trust cookies: how long a trusted browser skips the
# 2FA challenge (cookie is HttpOnly, SameSite=Lax, bound to one user).
TOTP_TRUST_DAYS = env_int("TOTP_TRUST_DAYS", 30)
# Daily security digest: how far back to summarize security events, and how
# long a user is quiet after one is sent (dedup for frequent cron runs).
SECURITY_DIGEST_WINDOW_HOURS = env_int("SECURITY_DIGEST_WINDOW_HOURS", 24)

# ---------------------------------------------------------------------------
# Verification reminders — nudges for accounts stuck unverified. The
# `send_verification_reminders` management command emails accounts whose
# verification is pending longer than AFTER hours, but never more than once
# per COOLDOWN hours per account.
# ---------------------------------------------------------------------------
VERIFY_REMINDER_AFTER_HOURS = env_int("VERIFY_REMINDER_AFTER_HOURS", 24)
VERIFY_REMINDER_COOLDOWN_HOURS = env_int("VERIFY_REMINDER_COOLDOWN_HOURS", 24)

# ---------------------------------------------------------------------------
# LLM configuration (hybrid screening). Optional — rule-based scoring always works.
# ---------------------------------------------------------------------------
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
