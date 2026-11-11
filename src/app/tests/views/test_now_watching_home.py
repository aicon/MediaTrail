from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.models import (
    DeviceDisplayName,
    Item,
    LivePlayback,
    LivePlaybackStatus,
    MediaTypes,
    Sources,
)
from app.playback_operations import clear_live_playback, upsert_live_playback

_LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "now-watching-home-tests",
    },
}


@override_settings(CACHES=_LOCMEM_CACHE)
class NowWatchingHomeTests(TestCase):
    """Home page Now Watching strip for movies and episodes."""

    def setUp(self):
        """Log in a user with movie and episode fixtures."""
        self.user = get_user_model().objects.create_user(
            username="home-live",
            password="12345",
        )
        self.client.login(username="home-live", password="12345")
        self.movie = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image="https://example.com/movie.jpg",
        )
        self.episode = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Starsky & Hutch",
            image="https://example.com/ep.jpg",
            season_number=2,
            episode_number=21,
        )
        self.meta_patcher = patch(
            "app.playback_operations.services.get_media_metadata",
            return_value={},
        )
        self.meta_patcher.start()
        self.addCleanup(self.meta_patcher.stop)

    def test_home_shows_movie_now_watching(self):
        """Movie session appears on home with percent and remaining."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=1_800_000,
            duration_ms=7_200_000,
            status=LivePlaybackStatus.WATCHING,
        )
        LivePlayback.objects.filter(user=self.user).update(year="1999")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Now Watching")
        self.assertContains(response, "Fight Club")
        self.assertContains(response, "1999")
        self.assertContains(response, "25%")
        self.assertContains(response, 'hx-get="/now-watching/"')
        self.assertContains(response, 'style="width: 25%"')

    def test_home_shows_episode_title_and_code(self):
        """Episode strip shows series title, SxxExx, and episode title."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=600_000,
            duration_ms=2_400_000,
            status=LivePlaybackStatus.PAUSED,
        )
        LivePlayback.objects.filter(user=self.user).update(
            episode_title="The Committee",
            year="1975 - 1979",
            poster_image="https://example.com/poster.jpg",
        )
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Paused")
        self.assertContains(response, "Starsky &amp; Hutch")
        self.assertContains(response, "S02E21")
        self.assertContains(response, "The Committee")
        self.assertNotContains(response, "21. epizód")
        self.assertContains(response, "1975 - 1979")
        self.assertContains(response, "25%")
        self.assertContains(response, 'style="width: 25%"')
        self.assertContains(response, 'style="--nw-pct: 25"')
        self.assertContains(response, "nw-card")
        self.assertContains(response, "nw-layout")
        self.assertContains(response, "nw-percent")
        self.assertContains(response, "nw-bar-fill")
        self.assertContains(response, 'hx-trigger="every 10s"')
        self.assertContains(response, "nw-episode-title")

    def test_placeholder_episode_title_hidden(self):
        """Generic 'N. epizód' labels are not rendered beside SxxExx."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=600_000,
            duration_ms=2_400_000,
            status=LivePlaybackStatus.WATCHING,
        )
        LivePlayback.objects.filter(user=self.user).update(episode_title="21. epizód")
        with patch(
            "app.home.refresh_playback_display",
            side_effect=lambda playback: playback,
        ):
            response = self.client.get(reverse("now_watching_partial"))
        self.assertContains(response, "S02E21")
        self.assertNotContains(response, "21. epizód")

    def test_pause_keeps_strip(self):
        """Paused status still renders the strip."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=50_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.PAUSED,
        )
        response = self.client.get(reverse("now_watching_partial"))
        self.assertContains(response, "Paused")
        self.assertContains(response, "Fight Club")

    def test_clear_removes_strip_without_history_side_effects(self):
        """Below-threshold stop clears the strip and leaves no live row."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=20_000,
            duration_ms=100_000,
        )
        clear_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
        )
        response = self.client.get(reverse("now_watching_partial"))
        self.assertContains(response, 'id="now-watching-strip"')
        self.assertNotContains(response, "Now Watching")
        self.assertNotContains(response, "Paused")
        self.assertFalse(LivePlayback.objects.filter(user=self.user).exists())

    def test_missing_duration_omits_percent_fill(self):
        """No duration → no bogus percent or progress width."""
        LivePlayback.objects.create(
            user=self.user,
            item=self.movie,
            position_ms=10_000,
            duration_ms=None,
            status=LivePlaybackStatus.WATCHING,
        )
        response = self.client.get(reverse("now_watching_partial"))
        self.assertContains(response, "Fight Club")
        self.assertNotContains(response, "%")
        self.assertNotContains(response, 'style="width:')

    @override_settings(LIVE_PLAYBACK_WATCHING_STALE_SECONDS=30)
    def test_stale_session_hidden(self):
        """Expired active sessions do not render on home."""
        playback = LivePlayback.objects.create(
            user=self.user,
            item=self.movie,
            position_ms=10_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.WATCHING,
        )
        LivePlayback.objects.filter(pk=playback.pk).update(
            updated_at=timezone.now() - timedelta(minutes=5),
        )
        response = self.client.get(reverse("now_watching_partial"))
        self.assertNotContains(response, "Fight Club")

    def test_now_watching_partial_empty(self):
        """Partial still returns the poll wrapper when nothing is live."""
        response = self.client.get(reverse("now_watching_partial"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="now-watching-strip"')
        self.assertNotContains(response, "Now Watching")

    def test_poster_and_title_share_detail_link(self):
        """Left poster uses the same detail URL as the title."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
        )
        response = self.client.get(reverse("now_watching_partial"))
        self.assertContains(response, 'class="nw-poster-link"')
        self.assertContains(response, 'class="nw-dismiss"')
        self.assertContains(response, 'class="nw-badge')
        self.assertNotContains(response, 'hx-post="/now-watching/toggle/"')
        self.assertContains(response, 'hx-post="/now-watching/dismiss/"')

    def test_dismiss_clears_strip(self):
        """X dismiss drops the live row without writing history."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
        )
        response = self.client.post(reverse("now_watching_dismiss"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="now-watching-strip"')
        self.assertNotContains(response, "Now Watching")
        self.assertFalse(LivePlayback.objects.filter(user=self.user).exists())

    def test_two_devices_show_two_strips(self):
        """Phone and TV sessions appear as separate cards."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
            device_id="phone-1",
            device_label="telefon",
        )
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=20_000,
            duration_ms=100_000,
            device_id="tv-1",
            device_label="TV",
        )
        LivePlayback.objects.filter(device_id="tv-1").update(
            episode_title="The Committee",
        )
        response = self.client.get(reverse("now_watching_partial"))
        self.assertContains(response, "Fight Club")
        self.assertContains(response, "Starsky &amp; Hutch")
        self.assertContains(response, "telefon")
        self.assertContains(response, "TV")
        self.assertContains(response, 'hx-vals=\'{"device_id": "phone-1"}\'')

    def test_dismiss_one_device_keeps_the_other(self):
        """Dismiss with device_id only clears that strip."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
            device_id="phone-1",
            device_label="telefon",
        )
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=40_000,
            duration_ms=100_000,
            device_id="tv-1",
            device_label="TV",
        )
        response = self.client.post(
            reverse("now_watching_dismiss"),
            {"device_id": "phone-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "telefon")
        self.assertContains(response, "TV")
        self.assertFalse(
            LivePlayback.objects.filter(user=self.user, device_id="phone-1").exists(),
        )
        self.assertTrue(
            LivePlayback.objects.filter(user=self.user, device_id="tv-1").exists(),
        )

    def test_rename_device_persists_across_strip(self):
        """Custom device names appear on the strip and survive empty live rows."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
            device_id="tv-living",
            device_label="TV · Shield",
        )
        response = self.client.post(
            reverse("now_watching_rename"),
            {"device_id": "tv-living", "custom_name": "Nappali TV"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nappali TV")
        self.assertEqual(
            DeviceDisplayName.objects.get(
                user=self.user,
                device_id="tv-living",
            ).custom_name,
            "Nappali TV",
        )
