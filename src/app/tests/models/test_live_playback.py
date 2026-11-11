from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils import translation

from app.models import Item, LivePlayback, LivePlaybackStatus, MediaTypes, Sources
from app.playback_operations import (
    clear_live_playback,
    get_now_watching,
    is_placeholder_episode_title,
    upsert_live_playback,
)


class LivePlaybackModelTests(TestCase):
    """Unit tests for LivePlayback helpers."""

    def setUp(self):
        """Create user and movie/episode items."""
        self.user = get_user_model().objects.create_user(username="live-user")
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
            title="Breaking Bad",
            image="https://example.com/ep.jpg",
            season_number=2,
            episode_number=21,
        )

    def test_percent_and_remaining_for_movie(self):
        """Movie percent and remaining labels are derived from ms fields."""
        playback = LivePlayback.objects.create(
            user=self.user,
            item=self.movie,
            position_ms=30 * 60_000,
            duration_ms=120 * 60_000,
            status=LivePlaybackStatus.WATCHING,
        )
        self.assertEqual(playback.percent_watched, 25)
        self.assertEqual(playback.remaining_label, "1H 30M LEFT")
        self.assertEqual(playback.remaining_short, "1H 30M")
        playback.position_ms = 0
        playback.duration_ms = 85 * 60_000
        with translation.override("hu"):
            self.assertEqual(playback.remaining_short, "1ó25p")
        self.assertEqual(playback.remaining_short, "1H 25M")
        self.assertIsNone(playback.season_episode_label)

    def test_missing_duration_hides_percent(self):
        """Invalid duration must not invent a percent or remaining time."""
        playback = LivePlayback.objects.create(
            user=self.user,
            item=self.movie,
            position_ms=90_000,
            duration_ms=None,
            status=LivePlaybackStatus.WATCHING,
        )
        self.assertIsNone(playback.percent_watched)
        self.assertIsNone(playback.remaining_ms)
        self.assertIsNone(playback.remaining_label)

        zero_duration = LivePlayback.objects.create(
            user=self.user,
            item=self.episode,
            device_id="episode-device",
            position_ms=90_000,
            duration_ms=0,
            status=LivePlaybackStatus.WATCHING,
        )
        self.assertIsNone(zero_duration.percent_watched)
        self.assertIsNone(zero_duration.remaining_ms)

    def test_progress_updates_percent_fill(self):
        """Progress upserts raise percent for the Simkl fill width."""
        first = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.WATCHING,
        )
        self.assertEqual(first.percent_watched, 10)
        second = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=40_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.WATCHING,
        )
        self.assertEqual(second.percent_watched, 40)
        self.assertEqual(second.remaining_short, "1M")

    def test_season_episode_label(self):
        """Episode sessions expose SxxExx."""
        playback = LivePlayback.objects.create(
            user=self.user,
            item=self.episode,
            position_ms=600_000,
            duration_ms=2_400_000,
            status=LivePlaybackStatus.PAUSED,
            episode_title="The Committee",
            year="1975 - 1979",
        )
        self.assertEqual(playback.season_episode_label, "S02E21")
        self.assertEqual(playback.percent_watched, 25)
        self.assertEqual(playback.remaining_label, "30M LEFT")
        self.assertEqual(playback.episode_title, "The Committee")

    def test_upsert_zero_position_guard(self):
        """Zero position updates keep the previous seek."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=90_000,
            duration_ms=7_200_000,
            status=LivePlaybackStatus.WATCHING,
        )
        playback = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=0,
            duration_ms=7_200_000,
            status=LivePlaybackStatus.PAUSED,
        )
        self.assertEqual(playback.position_ms, 90_000)
        self.assertEqual(playback.status, LivePlaybackStatus.PAUSED)

    def test_two_devices_same_item_keep_separate_rows(self):
        """The same title on two devices creates two live rows."""
        phone = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
            device_id="phone-1",
            device_label="telefon",
        )
        tv = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=40_000,
            duration_ms=100_000,
            device_id="tv-1",
            device_label="TV",
        )
        self.assertNotEqual(phone.id, tv.id)
        self.assertEqual(LivePlayback.objects.filter(user=self.user).count(), 2)
        self.assertEqual(phone.position_ms, 10_000)
        self.assertEqual(tv.position_ms, 40_000)

    def test_same_device_content_switch_updates_one_row(self):
        """One device switching titles updates its own row only."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
            media_id="550",
            position_ms=10_000,
            duration_ms=100_000,
            device_id="tv-1",
            device_label="TV",
        )
        other = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=5_000,
            duration_ms=100_000,
            device_id="phone-1",
            device_label="telefon",
        )
        switched = upsert_live_playback(
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
        self.assertEqual(LivePlayback.objects.filter(user=self.user).count(), 2)
        self.assertEqual(switched.item_id, self.episode.id)
        self.assertEqual(switched.position_ms, 20_000)
        other.refresh_from_db()
        self.assertEqual(other.position_ms, 5_000)

    def test_pause_keeps_row(self):
        """Pause keeps the live row so the strip can show PAUSED."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=50_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.WATCHING,
        )
        paused = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=50_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.PAUSED,
        )
        self.assertEqual(paused.status, LivePlaybackStatus.PAUSED)
        self.assertEqual(get_now_watching(self.user).id, paused.id)

    def test_now_watching_prefers_latest(self):
        """Hero candidate is the most recently updated session."""
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
            position_ms=50_000,
            duration_ms=100_000,
            device_id="tv-1",
            device_label="TV",
        )
        now = get_now_watching(self.user)
        self.assertEqual(now.item_id, self.episode.id)

    def test_clear_live_playback(self):
        """Clear removes the matching movie or episode row without history."""
        upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=50_000,
            duration_ms=100_000,
        )
        deleted = clear_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
        )
        self.assertEqual(deleted, 1)
        self.assertIsNone(get_now_watching(self.user))

    @override_settings(
        LIVE_PLAYBACK_WATCHING_STALE_SECONDS=60,
        LIVE_PLAYBACK_PAUSED_STALE_SECONDS=10 * 60,
    )
    def test_stale_watching_session_is_purged(self):
        """Orphan watching sessions older than the watching TTL are removed."""
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
        self.assertIsNone(get_now_watching(self.user))
        self.assertFalse(LivePlayback.objects.filter(pk=playback.pk).exists())

    @override_settings(
        LIVE_PLAYBACK_WATCHING_STALE_SECONDS=60,
        LIVE_PLAYBACK_PAUSED_STALE_SECONDS=10 * 60,
    )
    def test_paused_session_survives_watching_ttl(self):
        """Paused rows are not cleared by the short watching idle TTL."""
        playback = LivePlayback.objects.create(
            user=self.user,
            item=self.movie,
            position_ms=10_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.PAUSED,
        )
        LivePlayback.objects.filter(pk=playback.pk).update(
            updated_at=timezone.now() - timedelta(minutes=5),
        )
        self.assertEqual(get_now_watching(self.user).id, playback.id)
        self.assertTrue(LivePlayback.objects.filter(pk=playback.pk).exists())

    @override_settings(
        LIVE_PLAYBACK_WATCHING_STALE_SECONDS=60,
        LIVE_PLAYBACK_PAUSED_STALE_SECONDS=10 * 60,
    )
    def test_stale_paused_session_is_purged(self):
        """Paused sessions older than the paused TTL are removed."""
        playback = LivePlayback.objects.create(
            user=self.user,
            item=self.movie,
            position_ms=10_000,
            duration_ms=100_000,
            status=LivePlaybackStatus.PAUSED,
        )
        LivePlayback.objects.filter(pk=playback.pk).update(
            updated_at=timezone.now() - timedelta(minutes=15),
        )
        self.assertIsNone(get_now_watching(self.user))
        self.assertFalse(LivePlayback.objects.filter(pk=playback.pk).exists())

    def test_placeholder_episode_title_detection(self):
        """Localized 'N. epizód' labels are treated as placeholders."""
        self.assertTrue(is_placeholder_episode_title("21. epizód", 21))
        self.assertTrue(is_placeholder_episode_title("1. epizód", 1))
        self.assertTrue(is_placeholder_episode_title("2. rész", 2))
        self.assertTrue(is_placeholder_episode_title("Episode 21", 21))
        self.assertTrue(is_placeholder_episode_title(""))
        self.assertFalse(is_placeholder_episode_title("The Committee", 21))

    @patch("app.playback_operations._fetch_english_episode_title", return_value="")
    @patch("app.playback_operations.services.get_media_metadata")
    def test_episode_display_metadata(self, mock_meta, _english):
        """Episode upsert caches series year and the episode's own title."""
        mock_meta.return_value = {
            "title": "Starsky & Hutch",
            "image": "https://example.com/poster.jpg",
            "details": {
                "first_air_date": "1975-09-10",
                "last_air_date": "1979-05-15",
            },
            "season/2": {
                "image": "https://example.com/season.jpg",
                "episodes": [
                    {
                        "episode_number": 21,
                        "name": "The Committee",
                        "still_path": "/still.jpg",
                    },
                ],
            },
        }
        playback = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=100_000,
            duration_ms=1_000_000,
        )
        self.assertEqual(playback.episode_title, "The Committee")
        self.assertEqual(playback.year, "1975 - 1979")
        self.assertEqual(playback.poster_image, "https://example.com/poster.jpg")

    @patch(
        "app.playback_operations._fetch_english_episode_title",
        return_value="The Committee",
    )
    @patch("app.playback_operations.services.get_media_metadata")
    def test_replaces_localized_episode_placeholder(self, mock_meta, _english):
        """Stored '21. epizód' is replaced with the English episode title."""
        mock_meta.return_value = {
            "title": "Starsky & Hutch",
            "image": "https://example.com/poster.jpg",
            "details": {"first_air_date": "1975-09-10", "last_air_date": "1979-05-15"},
            "season/2": {
                "episodes": [
                    {
                        "episode_number": 21,
                        "name": "21. epizód",
                        "still_path": "/still.jpg",
                    },
                ],
            },
        }
        LivePlayback.objects.create(
            user=self.user,
            item=self.episode,
            position_ms=10_000,
            duration_ms=100_000,
            episode_title="21. epizód",
            status=LivePlaybackStatus.WATCHING,
        )
        playback = upsert_live_playback(
            user=self.user,
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
            media_id="1396",
            season_number=2,
            episode_number=21,
            position_ms=20_000,
            duration_ms=100_000,
        )
        self.assertEqual(playback.episode_title, "The Committee")
        self.assertFalse(
            is_placeholder_episode_title(playback.episode_title, 21),
        )
