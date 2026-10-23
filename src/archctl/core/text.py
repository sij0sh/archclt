"""Small presentation helpers shared by review renderers."""

from __future__ import annotations


def markdown_cell(value: object) -> str:
    """Render one table cell without breaking the Markdown row."""
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
