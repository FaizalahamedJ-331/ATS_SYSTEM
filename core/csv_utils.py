"""Helpers for safe CSV export.

Cells that begin with = + - @ or tab are interpreted as formulas by
spreadsheet apps (Excel / LibreOffice / Google Sheets). Prefixing them
with a single quote neutralizes that while keeping the visible value
unchanged.
"""

import re

_DANGEROUS_START = re.compile(r"^[=+\-@\t]")


def safe_csv_cell(value):
    """Return ``value`` guarded against spreadsheet formula injection."""
    if value is None:
        return ""
    text = str(value)
    return "'" + text if _DANGEROUS_START.match(text) else text
