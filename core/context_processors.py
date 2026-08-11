"""Template context processors for TalentPulse."""
from django.conf import settings


# Settings exposed to every template as top-level context variables.
# Keep this list explicit and small - never dump the whole settings module.
PUBLIC_SETTINGS = (
    "PASSWORD_MIN_LENGTH",
    "SITE_URL",
)


def public_settings(request):
    """Expose a whitelist of settings to templates (e.g. {{ PASSWORD_MIN_LENGTH }})."""
    return {name: getattr(settings, name, None) for name in PUBLIC_SETTINGS}
