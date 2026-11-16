"""Interface languages. English is the source language and the fallback."""

from django.utils.translation import get_language_from_request, gettext_lazy as _

LANGUAGE_AUTO = "auto"

LANGUAGE_CHOICES = (
    ("de", "Deutsch"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("hu", "Magyar"),
    ("it", "Italiano"),
)

LANGUAGE_CODES = frozenset(code for code, _label in LANGUAGE_CHOICES)

# Native names stay untranslated. Auto is the only label that follows the UI language.
INTERFACE_LANGUAGE_CHOICES = (
    (LANGUAGE_AUTO, _("Auto (browser language)")),
    *LANGUAGE_CHOICES,
)


def resolve_interface_language(request, selected):
    """Return a catalog language. Auto follows the browser, then English."""
    if selected in LANGUAGE_CODES:
        return selected
    detected = get_language_from_request(request, check_path=False) or ""
    code = detected.split("-")[0]
    if code in LANGUAGE_CODES:
        return code
    return "en"

DOCS_SITE = "https://aicon.github.io/mediatrail-docs"
# Languages that have their own book. Every other interface language uses English.
DOCS_LANGUAGES = frozenset({"hu"})
