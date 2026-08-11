"""Tests for the strong-password policy (diversity validator + settings)."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from core.validators import CharacterDiversityValidator, character_classes_present


class CharacterClassCountTests(SimpleTestCase):
    def test_counts_each_class_once(self):
        self.assertEqual(character_classes_present("abc"), 1)          # lower only
        self.assertEqual(character_classes_present("abcABC"), 2)      # lower+upper
        self.assertEqual(character_classes_present("abc123"), 2)      # lower+digits
        self.assertEqual(character_classes_present("abc123!"), 3)     # +symbols
        self.assertEqual(character_classes_present("aB1!"), 4)
        self.assertEqual(character_classes_present(""), 0)


class CharacterDiversityValidatorTests(SimpleTestCase):
    def setUp(self):
        self.validator = CharacterDiversityValidator()

    def test_rejects_single_class_even_if_long(self):
        # Long but one-class passwords must still fail.
        with self.assertRaises(ValidationError):
            self.validator.validate("aaaaaaaaaaaa")
        with self.assertRaises(ValidationError):
            self.validator.validate("12345678901234567890")

    def test_rejects_two_class_passwords(self):
        with self.assertRaises(ValidationError):
            self.validator.validate("lowerupper")

    def test_accepts_three_classes(self):
        self.validator.validate("lowerUPPER123")
        self.validator.validate("abCD12!")

    def test_help_text_mentions_min_classes(self):
        self.assertIn("3", self.validator.get_help_text())


class PolicyIntegrationTests(SimpleTestCase):
    """The configured AUTH_PASSWORD_VALIDATORS reject weak passwords."""

    def test_strong_password_passes_all_validators(self):
        # 4 classes, 12 chars, not common, not numeric.
        validate_password("Tr0ub4dor!2026")

    def test_all_lowercase_fails(self):
        with self.assertRaises(ValidationError):
            validate_password("passwordpassword")

    def test_short_but_diverse_fails_length(self):
        with self.assertRaises(ValidationError):
            validate_password("Ab1!")

    def test_common_password_fails(self):
        with self.assertRaises(ValidationError):
            validate_password("Password123")

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {
                "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                "OPTIONS": {"min_length": 12},
            },
        ]
    )
    def test_override_min_length_honored(self):
        # 10 chars would pass the 10-char default but not 12.
        with self.assertRaises(ValidationError):
            validate_password("Abcdef1234")
        validate_password("Abcdef123456")
