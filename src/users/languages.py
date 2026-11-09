"""Interface languages. English is the source language and the fallback."""

LANGUAGE_CHOICES = (
    ("en", "English"),
    ("hu", "Magyar"),
)

LANGUAGE_CODES = frozenset(code for code, _label in LANGUAGE_CHOICES)
