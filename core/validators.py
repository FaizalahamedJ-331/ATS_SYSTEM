"""Custom password validators.

The stock Django validators cover length, common passwords and numeric-only
passwords; the diversity validator below adds the missing "mix of character
kinds" rule so a single-character-class password like "aaaaaaaaaaaa" can never
pass just by being long enough.
"""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


CHARACTER_CLASSES = [
    (re.compile(r"[a-z]"), _("lowercase letters")),
    (re.compile(r"[A-Z]"), _("uppercase letters")),
    (re.compile(r"\d"), _("numbers")),
    (re.compile(r"[^A-Za-z0-9]"), _("symbols")),
]


def character_classes_present(password):
    """Return the number of distinct character classes in ``password`` (0-4)."""
    return sum(1 for pattern, _ in CHARACTER_CLASSES if pattern.search(password))


class CharacterDiversityValidator:
    """Require at least ``min_classes`` different character kinds.

    Default: at least 3 of {lowercase, uppercase, digits, symbols} - a
    password can no longer be all lowercase (or all digits, or only letters).
    """

    def __init__(self, min_classes=3):
        self.min_classes = min_classes

    def validate(self, password, user=None):
        if character_classes_present(password) < self.min_classes:
            raise ValidationError(
                _("Your password must include at least %(min_classes)s different "
                  "character types (e.g. lowercase, uppercase, numbers, symbols)."),
                code="password_too_simple",
                params={"min_classes": self.min_classes},
            )

    def get_help_text(self):
        return _(
            "Your password must mix at least %(min_classes)s character types "
            "(lowercase, uppercase, numbers, symbols)."
        ) % {"min_classes": self.min_classes}
