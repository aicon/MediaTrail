"""Interface languages. English is the source language and the fallback."""

LANGUAGE_CHOICES = (
    ("en", "English"),
    ("hu", "Magyar"),
)

LANGUAGE_CODES = frozenset(code for code, _label in LANGUAGE_CHOICES)

DOCS_SITE = "https://aicon.github.io/mediatrail-docs"
# Languages that have their own book. Every other interface language uses English.
DOCS_LANGUAGES = frozenset({"hu"})
