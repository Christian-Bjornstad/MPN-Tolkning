from __future__ import annotations

from typing import Any


def safe_excel_value(value: Any) -> Any:
    """Keep untrusted text inert when an XLSX is opened in spreadsheet software."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
