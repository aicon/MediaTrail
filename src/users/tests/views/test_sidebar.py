from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from app.models import MediaTypes
from users.models import WeekStartDayChoices


class SidebarViewTests(TestCase):
    """Tests for the sidebar view."""

    def setUp(self):
        """Create user for the tests."""
        self.watch_regions_patcher = patch(
            "users.views.tmdb.watch_provider_regions",
            return_value=[("UNSET", "Disabled"), ("US", "United States")],
        )
        self.watch_regions_patcher.start()
        self.addCleanup(self.watch_regions_patcher.stop)

        self.credentials = {"username": "testuser", "password": "testpass123"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def test_preferences_get(self):
        """Test GET request to preferences view."""
        response = self.client.get(reverse("preferences"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/preferences.html")

        self.assertIn("media_types", response.context)
        self.assertIn(MediaTypes.TV.value, response.context["media_types"])
        self.assertIn(MediaTypes.MOVIE.value, response.context["media_types"])
        self.assertNotIn(MediaTypes.EPISODE.value, response.context["media_types"])
        self.assertContains(response, 'name="language"')
        self.assertContains(response, "Auto (browser language)")
        self.assertContains(response, "Magyar")

    def test_language_preference_switches_the_interface(self):
        """Hungarian preference translates the preferences page."""
        response = self.client.post(
            reverse("preferences"),
            {
                "language": "hu",
                "media_types_checkboxes": [MediaTypes.TV.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.language, "hu")

        page = self.client.get(reverse("preferences"))
        self.assertContains(page, "Nyelv")
        self.assertContains(page, "Beállítások")

    def test_unknown_language_is_ignored(self):
        """A language outside the supported set does not replace the saved one."""
        self.user.language = "en"
        self.user.save()

        self.client.post(reverse("preferences"), {"language": "xx"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.language, "en")

    def test_auto_language_follows_the_browser(self):
        """Auto uses the browser language and can be overridden by a fixed choice."""
        self.user.language = "auto"
        self.user.save()

        hungarian = self.client.get(
            reverse("preferences"),
            HTTP_ACCEPT_LANGUAGE="hu",
        )
        self.assertContains(hungarian, "Nyelv")

        self.user.language = "en"
        self.user.save()
        fixed = self.client.get(
            reverse("preferences"),
            HTTP_ACCEPT_LANGUAGE="hu",
        )
        self.assertContains(fixed, "Language")
        self.assertNotContains(fixed, "Nyelv")

    def test_sidebar_post_update_preferences(self):
        """Test POST request to update preferences."""
        self.user.tv_enabled = True
        self.user.movie_enabled = True
        self.user.anime_enabled = True
        self.user.save()

        response = self.client.post(
            reverse("preferences"),
            {
                "media_types_checkboxes": [MediaTypes.TV.value, MediaTypes.ANIME.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.tv_enabled)
        self.assertFalse(self.user.movie_enabled)
        self.assertTrue(self.user.anime_enabled)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Settings updated", str(messages[0]))

    def test_sidebar_post_demo_user(self):
        """Test POST request from a demo user to preferences."""
        self.user.is_demo = True
        self.user.tv_enabled = True
        self.user.movie_enabled = False
        self.user.save()

        response = self.client.post(
            reverse("preferences"),
            {
                "media_types_checkboxes": [MediaTypes.TV.value, MediaTypes.MOVIE.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.tv_enabled)
        self.assertFalse(self.user.movie_enabled)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("view-only for demo accounts", str(messages[0]))

    def test_obfuscate_unseen_episodes_post_enable(self):
        """Test enabling obfuscate_unseen_episodes via preferences."""
        self.user.obfuscate_unseen_episodes = False
        self.user.save()

        response = self.client.post(
            reverse("preferences"),
            {
                "obfuscate_unseen_episodes": "on",
                "media_types_checkboxes": [MediaTypes.TV.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.obfuscate_unseen_episodes)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Settings updated", str(messages[0]))

    def test_obfuscate_unseen_episodes_post_disable(self):
        """Test disabling obfuscate_unseen_episodes via preferences."""
        self.user.obfuscate_unseen_episodes = True
        self.user.save()

        response = self.client.post(
            reverse("preferences"),
            {
                "media_types_checkboxes": [MediaTypes.TV.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertFalse(self.user.obfuscate_unseen_episodes)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Settings updated", str(messages[0]))

    def test_clickable_media_cards_and_obfuscate_unseen_episodes(self):
        """Test updating both clickable_media_cards and obfuscate_unseen_episodes."""
        self.user.clickable_media_cards = False
        self.user.obfuscate_unseen_episodes = False
        self.user.save()

        response = self.client.post(
            reverse("preferences"),
            {
                "clickable_media_cards": "on",
                "obfuscate_unseen_episodes": "on",
                "media_types_checkboxes": [MediaTypes.TV.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.clickable_media_cards)
        self.assertTrue(self.user.obfuscate_unseen_episodes)

    def test_obfuscate_unseen_episodes_post_demo_user(self):
        """Test that demo users cannot update obfuscate_unseen_episodes."""
        self.user.is_demo = True
        self.user.obfuscate_unseen_episodes = False
        self.user.save()

        response = self.client.post(
            reverse("preferences"),
            {
                "obfuscate_unseen_episodes": "on",
                "media_types_checkboxes": [MediaTypes.TV.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertFalse(self.user.obfuscate_unseen_episodes)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("view-only for demo accounts", str(messages[0]))

    def test_post_updates_week_start_day_valid(self):
        """Posting a valid week_start_day updates the user preference."""
        self.assertEqual(self.user.week_start_day, WeekStartDayChoices.MONDAY)
        response = self.client.post(
            reverse("preferences"),
            {
                "media_types_checkboxes": [MediaTypes.TV.value],
                "week_start_day": WeekStartDayChoices.SUNDAY,
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertEqual(self.user.week_start_day, WeekStartDayChoices.SUNDAY)

    def test_post_ignores_invalid_week_start_day(self):
        """Posting an invalid week_start_day leaves the value unchanged."""
        self.user.week_start_day = WeekStartDayChoices.SUNDAY
        self.user.save()

        response = self.client.post(
            reverse("preferences"),
            {
                "media_types_checkboxes": [MediaTypes.TV.value],
                "week_start_day": "saturday",
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertEqual(self.user.week_start_day, WeekStartDayChoices.SUNDAY)

    def test_theme_preference_is_saved_and_applied(self):
        """A saved theme is stored on the user and rendered before paint."""
        response = self.client.post(
            reverse("preferences"),
            {
                "language": "en",
                "theme": "light",
                "media_types_checkboxes": [MediaTypes.TV.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "light")

        page = self.client.get(reverse("preferences"))
        self.assertContains(page, 'data-theme="light"')
        self.assertContains(page, 'name="theme"')

    def test_invalid_theme_is_ignored(self):
        """A theme outside the three choices does not replace the saved one."""
        self.user.theme = "dark"
        self.user.save()

        self.client.post(
            reverse("preferences"),
            {
                "language": "en",
                "theme": "sepia",
                "media_types_checkboxes": [MediaTypes.TV.value],
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "dark")

    def test_header_theme_endpoint_saves_only_theme(self):
        """The header switcher endpoint updates theme without other preferences."""
        self.user.theme = "dark"
        self.user.language = "en"
        self.user.clickable_media_cards = False
        self.user.save()

        response = self.client.post(
            reverse("update_theme"),
            {"theme": "system"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "theme": "system"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "system")
        self.assertEqual(self.user.language, "en")
        self.assertFalse(self.user.clickable_media_cards)

        home = self.client.get(reverse("home"))
        self.assertContains(home, 'data-theme="system"')
        self.assertContains(home, 'aria-label="System theme"')
        self.assertContains(home, 'aria-label="Light theme"')
        self.assertContains(home, 'aria-label="Dark theme"')

    def test_header_theme_endpoint_rejects_invalid_value(self):
        """Invalid theme values leave the saved theme unchanged."""
        self.user.theme = "light"
        self.user.save()

        response = self.client.post(
            reverse("update_theme"),
            {"theme": "sepia"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(response.json()["theme"], "light")

        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, "light")

    def test_detail_link_preferences_are_saved(self):
        """External detail-link toggles persist without changing other prefs."""
        self.user.link_imdb_enabled = True
        self.user.link_port_hu_enabled = False
        self.user.save()

        response = self.client.post(
            reverse("preferences"),
            {
                "language": "en",
                "theme": "dark",
                "media_types_checkboxes": [MediaTypes.TV.value],
                "detail_links_form": "1",
                "detail_link_checkboxes": ["imdb", "port_hu"],
            },
        )
        self.assertRedirects(response, reverse("preferences"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.link_imdb_enabled)
        self.assertTrue(self.user.link_port_hu_enabled)
        self.assertFalse(self.user.link_wikidata_enabled)
        self.assertFalse(self.user.link_trakt_enabled)
        self.assertFalse(self.user.link_letterboxd_enabled)

        page = self.client.get(reverse("preferences"))
        self.assertContains(page, "External detail links")
        self.assertContains(page, 'name="detail_link_checkboxes"')
        self.assertNotContains(page, 'value="simkl"')
