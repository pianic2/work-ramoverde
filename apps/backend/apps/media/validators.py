"""Plain-text validation shared by media metadata and CMS content.

Content is rendered as text by the clients, never as HTML. These checks reject markup
and script-bearing URL schemes anyway, so stored values are safe even if a future
renderer forgets to escape.
"""

import re

from django.core.exceptions import ValidationError

# A tag, closing tag, comment, doctype or processing instruction: "<" followed by a letter,
# "/", "!" or "?". A lone "<" (e.g. "3 < 5") stays allowed.
_MARKUP = re.compile(r"<\s*[a-zA-Z/!?]")
_SCRIPT_SCHEME = re.compile(r"(?:java|vb)script\s*:|data\s*:\s*text/html", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def plain_text_error(value: str, *, multiline: bool = False) -> str | None:
    """Return a human message when `value` is not acceptable plain text, else None."""
    if _MARKUP.search(value):
        return "Markup (HTML, SVG, XML tags) is not allowed; use plain text."
    if _SCRIPT_SCHEME.search(value):
        return "Script URLs are not allowed."
    if _CONTROL.search(value):
        return "Control characters are not allowed."
    if not multiline and ("\n" in value or "\r" in value):
        return "Line breaks are not allowed in this field."
    return None


def validate_plain_text(value: str) -> None:
    message = plain_text_error(value)
    if message:
        raise ValidationError(message, code="unsafe_text")


def validate_multiline_plain_text(value: str) -> None:
    message = plain_text_error(value, multiline=True)
    if message:
        raise ValidationError(message, code="unsafe_text")
