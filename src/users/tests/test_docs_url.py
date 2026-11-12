from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from django.utils import translation


class DocsUrlTagTests(SimpleTestCase):
    """docs_url follows the active interface language."""

    def _render(self, language):
        with translation.override(language):
            return Template("{% load user_tags %}{% docs_url %}").render(Context())

    @override_settings(LANGUAGE_CODE="en")
    def test_english_manual_root(self):
        self.assertEqual(
            self._render("en"),
            "https://aicon.github.io/mediatrail-docs/",
        )

    def test_hungarian_manual_root(self):
        self.assertEqual(
            self._render("hu"),
            "https://aicon.github.io/mediatrail-docs/hu/",
        )
