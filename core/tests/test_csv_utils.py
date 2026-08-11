from django.test import SimpleTestCase

from core.csv_utils import safe_csv_cell


class SafeCsvCellTests(SimpleTestCase):
    def test_neutralizes_formula_characters(self):
        self.assertEqual(safe_csv_cell('=HYPERLINK("http://evil.com")'), "'=HYPERLINK(\"http://evil.com\")")
        self.assertEqual(safe_csv_cell("+SUM(A1:A9)"), "'+SUM(A1:A9)")
        self.assertEqual(safe_csv_cell("-2+3"), "'-2+3")
        self.assertEqual(safe_csv_cell("@import"), "'@import")
        self.assertEqual(safe_csv_cell("\tcmd"), "'\tcmd")

    def test_leaves_normal_values_untouched(self):
        self.assertEqual(safe_csv_cell("John Doe"), "John Doe")
        self.assertEqual(safe_csv_cell("3+ years"), "3+ years")
        self.assertEqual(safe_csv_cell("Backend Developer"), "Backend Developer")
        self.assertEqual(safe_csv_cell("51.2"), "51.2")
        self.assertEqual(safe_csv_cell(86), "86")

    def test_handles_empty_and_none(self):
        self.assertEqual(safe_csv_cell(""), "")
        self.assertEqual(safe_csv_cell(None), "")
