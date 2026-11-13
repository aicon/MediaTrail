"""Tests for Nuvio playback received by MediaTrail itself."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.models import Item, LivePlaybackStatus, MediaTypes, Movie, Sources, Status, TV
from integrations.models import NuvioAccount
from integrations.imports import helpers as import_helpers
from lists.models import CustomList, CustomListItem


class NuvioPlayerTests(TestCase):
    """Player events update Now Watching without a separate scrobbler."""

    def setUp(self):
        """Create the account that receives Nuvio playback."""
        self.user = get_user_model().objects.create_user(
            username="nuvio-user",
            password="testpass123",
        )
        self.movie_item = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image="http://example.com/fc.jpg",
        )

    @override_settings(URLS=["https://mediatrail.example"])
    def test_manifest_includes_account_token_and_logo(self):
        """The Integrations URL embeds this account token and points at the logo."""
        response = self.client.get(
            reverse("nuvio_manifest", kwargs={"token": self.user.token}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.user.token, response.request["PATH_INFO"])
        body = response.json()
        self.assertEqual(body["resources"], ["player"])
        self.assertEqual(
            body["logo"],
            "https://mediatrail.example/static/nuvio/logo.png",
        )

    @patch("integrations.nuvio_player.upsert_live_playback")
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [{"id": 550}], "tv_results": []},
    )
    def test_progress_updates_now_watching(self, _find, mock_upsert):
        """A progress event writes the live playback row for the URL account."""
        response = self.client.get(
            reverse(
                "nuvio_player",
                kwargs={
                    "token": self.user.token,
                    "media_type": "movie",
                    "video_id": "tt0137523",
                    "extra": "action=progress&currentTime=12000&duration=1800000.json",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_upsert.call_args.kwargs["user"], self.user)
        self.assertEqual(
            mock_upsert.call_args.kwargs["media_id"],
            "550",
        )
        self.assertEqual(mock_upsert.call_args.kwargs["position_ms"], 12000)
        self.assertEqual(
            mock_upsert.call_args.kwargs["status"],
            LivePlaybackStatus.WATCHING,
        )
        self.assertEqual(mock_upsert.call_args.kwargs["device_id"], "legacy")

    @patch("integrations.nuvio_player.upsert_live_playback")
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [], "tv_results": [{"id": 888}]},
    )
    def test_encoded_series_id_updates_now_watching(self, _find, mock_upsert):
        """Nuvio encodes episode colons; the scrobbler unquoted them first."""
        response = self.client.get(
            f"/nuvio/{self.user.token}/player/series/tt0072567%3A2%3A21/"
            "action=progress&currentTime=590000&duration=2842000.json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_upsert.call_args.kwargs["media_id"], "888")
        self.assertEqual(mock_upsert.call_args.kwargs["season_number"], 2)
        self.assertEqual(mock_upsert.call_args.kwargs["episode_number"], 21)
        self.assertEqual(mock_upsert.call_args.kwargs["position_ms"], 590000)

    @patch("integrations.nuvio_player.upsert_live_playback")
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [{"id": 550}], "tv_results": []},
    )
    def test_player_event_stays_on_the_token_account(self, _find, mock_upsert):
        """With two MediaTrail users, playback follows the token in the URL."""
        other = get_user_model().objects.create_user(
            username="other-user",
            password="testpass123",
        )
        response = self.client.get(
            reverse(
                "nuvio_player",
                kwargs={
                    "token": other.token,
                    "media_type": "movie",
                    "video_id": "tt0137523",
                    "extra": "action=progress&currentTime=5000&duration=100000.json",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_upsert.call_args.kwargs["user"], other)
        self.assertNotEqual(mock_upsert.call_args.kwargs["user"], self.user)

    @patch("integrations.nuvio_player.upsert_live_playback")
    def test_untokened_player_ignored_when_multiple_users(self, mock_upsert):
        """Legacy URL without a token must not guess among several accounts."""
        get_user_model().objects.create_user(
            username="second-user",
            password="testpass123",
        )
        response = self.client.get(
            reverse(
                "nuvio_player_legacy",
                kwargs={
                    "media_type": "movie",
                    "video_id": "tt0137523",
                    "extra": "action=progress&currentTime=5000&duration=100000.json",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        mock_upsert.assert_not_called()

    @patch("integrations.nuvio_player.clear_live_playback")
    @patch(
        "integrations.nuvio_player.resolve_playback_item",
    )
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [{"id": 550}], "tv_results": []},
    )
    def test_stop_mid_movie_saves_in_progress_resume(self, _find, mock_resolve, _clear):
        """Stop between 2% and 90% keeps the movie on the In Progress list."""
        mock_resolve.return_value = self.movie_item
        response = self.client.get(
            reverse(
                "nuvio_player",
                kwargs={
                    "token": self.user.token,
                    "media_type": "movie",
                    "video_id": "tt0137523",
                    "extra": "action=stop&currentTime=900000&duration=1800000.json",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        movie = Movie.objects.get(user=self.user, item=self.movie_item)
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)
        self.assertEqual(movie.resume_position_ms, 900000)
        self.assertEqual(movie.resume_duration_ms, 1800000)
        self.assertEqual(movie.resume_bar_percent, 50)

    @patch("integrations.nuvio_player.clear_live_playback")
    @patch(
        "integrations.nuvio_player.resolve_playback_item",
    )
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [{"id": 550}], "tv_results": []},
    )
    def test_stop_near_start_skips_resume(self, _find, mock_resolve, _clear):
        """Tiny progress should not create an In Progress resume row."""
        mock_resolve.return_value = self.movie_item
        response = self.client.get(
            reverse(
                "nuvio_player",
                kwargs={
                    "token": self.user.token,
                    "media_type": "movie",
                    "video_id": "tt0137523",
                    "extra": "action=stop&currentTime=1000&duration=1800000.json",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Movie.objects.filter(user=self.user, item=self.movie_item).exists(),
        )

    @patch("app.models.providers.services.get_media_metadata", return_value={"max_progress": 1})
    @patch("integrations.nuvio_player.clear_live_playback")
    @patch(
        "integrations.nuvio_player.resolve_playback_item",
    )
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [{"id": 550}], "tv_results": []},
    )
    def test_stop_finished_movie_clears_resume(
        self,
        _find,
        mock_resolve,
        _clear,
        _metadata,
    ):
        """≥90% stop completes the movie and clears resume fields."""
        mock_resolve.return_value = self.movie_item
        Movie.objects.create(
            user=self.user,
            item=self.movie_item,
            status=Status.IN_PROGRESS.value,
            resume_position_ms=500000,
            resume_duration_ms=1800000,
        )
        response = self.client.get(
            reverse(
                "nuvio_player",
                kwargs={
                    "token": self.user.token,
                    "media_type": "movie",
                    "video_id": "tt0137523",
                    "extra": "action=stop&currentTime=1700000&duration=1800000.json",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        movie = Movie.objects.get(user=self.user, item=self.movie_item)
        self.assertEqual(movie.status, Status.COMPLETED.value)
        self.assertIsNone(movie.resume_position_ms)
        self.assertIsNone(movie.resume_duration_ms)
        self.assertIsNone(movie.resume_bar_percent)

    @patch(
        "app.models.providers.services.get_media_metadata",
        return_value={"max_progress": 1},
    )
    def test_mark_completed_in_mediatrail_clears_resume(self, _metadata):
        """UI / form save to Completed drops the home In Progress resume card."""
        movie = Movie.objects.create(
            user=self.user,
            item=self.movie_item,
            status=Status.IN_PROGRESS.value,
            resume_position_ms=400000,
            resume_duration_ms=1800000,
        )
        movie.status = Status.COMPLETED.value
        movie.save()
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.COMPLETED.value)
        self.assertIsNone(movie.resume_position_ms)
        self.assertIsNone(movie.resume_duration_ms)

    @patch(
        "app.models.providers.services.get_media_metadata",
        return_value={"max_progress": 1},
    )
    def test_new_completed_entry_removes_in_progress_sibling(self, _metadata):
        """Add new entry → Completed deletes the prior mid-watch In Progress row."""
        mid_watch = Movie.objects.create(
            user=self.user,
            item=self.movie_item,
            status=Status.IN_PROGRESS.value,
            resume_position_ms=2_954_100,
            resume_duration_ms=7_567_309,
        )
        finished = Movie(
            user=self.user,
            item=self.movie_item,
            status=Status.COMPLETED.value,
        )
        finished.save()

        self.assertFalse(Movie.objects.filter(pk=mid_watch.pk).exists())
        self.assertEqual(Movie.objects.filter(item=self.movie_item).count(), 1)
        finished.refresh_from_db()
        self.assertEqual(finished.status, Status.COMPLETED.value)
        self.assertIsNone(finished.resume_position_ms)


def _tv_metadata_for_resume(*_args, **_kwargs):
    """Enough TMDB-shaped metadata for Season create + get_tv."""
    return {
        "title": "Test Show",
        "image": "http://example.com/show.jpg",
        "details": {"seasons": 1},
        "max_progress": 6,
        "season/1": {
            "image": "http://example.com/s1.jpg",
            "episodes": [
                {"episode_number": 1, "air_date": "2020-01-01", "image": "x.jpg"},
                {"episode_number": 2, "air_date": "2020-01-02", "image": "x.jpg"},
                {"episode_number": 6, "air_date": "2020-01-06", "image": "x.jpg"},
            ],
        },
        "related": {
            "seasons": [{"season_number": 1, "image": "http://example.com/s1.jpg"}],
        },
    }


class NuvioEpisodeResumeTests(TestCase):
    """Episode mid-watch resume lands on the Season home card."""

    def setUp(self):
        """Create the account that receives Nuvio playback."""
        self.user = get_user_model().objects.create_user(
            username="nuvio-episode-user",
            password="testpass123",
        )

    @patch("integrations.nuvio_player.upsert_live_playback")
    @patch(
        "app.models.providers.services.get_media_metadata",
        side_effect=_tv_metadata_for_resume,
    )
    @patch(
        "app.episode_operations.services.get_media_metadata",
        side_effect=_tv_metadata_for_resume,
    )
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [], "tv_results": [{"id": 1396}]},
    )
    def test_episode_start_removes_show_from_watchlist_and_nuvio(
        self,
        _find,
        _ep_meta,
        _model_meta,
        _upsert,
    ):
        """Starting any episode drops the parent TV from Watchlist + Library."""
        self.user.nuvio_sync_library_enabled = True
        self.user.save(update_fields=["nuvio_sync_library_enabled"])
        account = NuvioAccount.objects.create(
            user=self.user,
            email=import_helpers.encrypt("a@b.c"),
            password=import_helpers.encrypt("pw"),
            profile_id=1,
        )
        watchlist = CustomList.objects.create(name="WL", owner=self.user)
        account.watchlist_list = watchlist
        account.imdb_map = {"tt0903747": "1396"}
        account.save(update_fields=["watchlist_list", "imdb_map"])
        tv_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image="",
        )
        TV.objects.create(
            user=self.user,
            item=tv_item,
            status=Status.PLANNING.value,
        )
        CustomListItem.objects.create(custom_list=watchlist, item=tv_item)

        with patch("integrations.tasks.delete_nuvio_library_item.delay") as mock_delay:
            with patch(
                "integrations.nuvio_library.resolve_imdb_id_cached",
                return_value="tt0903747",
            ):
                response = self.client.get(
                    reverse(
                        "nuvio_player",
                        kwargs={
                            "token": self.user.token,
                            "media_type": "series",
                            "video_id": "tt0903747:1:1",
                            "extra": "action=start&currentTime=0&duration=1800000.json",
                        },
                    ),
                )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CustomListItem.objects.filter(custom_list=watchlist, item=tv_item).exists(),
        )
        mock_delay.assert_called()
        deleted_ids = {k["content_id"] for k in mock_delay.call_args.args[1]}
        self.assertEqual(
            deleted_ids,
            {"tt0903747", "imdb:tt0903747", "tmdb:1396"},
        )

    @patch("integrations.nuvio_player.clear_live_playback")
    @patch(
        "app.models.providers.services.get_media_metadata",
        side_effect=_tv_metadata_for_resume,
    )
    @patch(
        "app.episode_operations.services.get_media_metadata",
        side_effect=_tv_metadata_for_resume,
    )
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [], "tv_results": [{"id": 1396}]},
    )
    def test_stop_mid_episode_saves_season_resume(
        self,
        _find,
        _ep_meta,
        _model_meta,
        _clear,
    ):
        """Stop between 2% and 90% stores resume on the Season, not an Episode."""
        from app.models import Episode, Season

        response = self.client.get(
            reverse(
                "nuvio_player",
                kwargs={
                    "token": self.user.token,
                    "media_type": "series",
                    "video_id": "tt0903747:1:6",
                    "extra": "action=stop&currentTime=756000&duration=1800000.json",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        season = Season.objects.get(user=self.user, item__media_id="1396")
        self.assertEqual(season.status, Status.IN_PROGRESS.value)
        self.assertEqual(season.resume_episode_number, 6)
        self.assertEqual(season.resume_position_ms, 756000)
        self.assertEqual(season.resume_duration_ms, 1800000)
        self.assertEqual(season.resume_bar_percent, 42)
        self.assertIsNotNone(season.resume_updated_at)
        self.assertFalse(Episode.objects.filter(related_season=season).exists())

    @patch("integrations.nuvio_player.upsert_live_playback")
    @patch("integrations.nuvio_player.clear_live_playback")
    @patch(
        "app.models.providers.services.get_media_metadata",
        side_effect=_tv_metadata_for_resume,
    )
    @patch(
        "app.episode_operations.services.get_media_metadata",
        side_effect=_tv_metadata_for_resume,
    )
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [], "tv_results": [{"id": 1396}]},
    )
    def test_pause_mid_episode_saves_season_resume(
        self,
        _find,
        _ep_meta,
        _model_meta,
        _clear,
        _upsert,
    ):
        """Pause mid-episode also upserts Season resume."""
        from app.models import Season

        response = self.client.get(
            reverse(
                "nuvio_player",
                kwargs={
                    "token": self.user.token,
                    "media_type": "series",
                    "video_id": "tt0903747:1:6",
                    "extra": "action=pause&currentTime=900000&duration=1800000.json",
                },
            ),
        )
        self.assertEqual(response.status_code, 200)
        season = Season.objects.get(user=self.user, item__media_id="1396")
        self.assertEqual(season.resume_episode_number, 6)
        self.assertEqual(season.resume_position_ms, 900000)

    @patch("integrations.nuvio_outbound.enqueue_watched_upsert")
    @patch("integrations.nuvio_player.clear_live_playback")
    @patch(
        "app.models.providers.services.get_media_metadata",
        side_effect=_tv_metadata_for_resume,
    )
    @patch(
        "app.episode_operations.services.get_media_metadata",
        side_effect=_tv_metadata_for_resume,
    )
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [], "tv_results": [{"id": 1396}]},
    )
    def test_stop_finished_episode_clears_resume(
        self,
        _find,
        _ep_meta,
        _model_meta,
        _clear,
        _enqueue,
    ):
        """≥90% stop watches the episode and clears Season resume."""
        from app.models import Item, Season, TV

        tv_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test Show",
            image="http://example.com/show.jpg",
        )
        tv = TV.objects.create(
            user=self.user,
            item=tv_item,
            status=Status.IN_PROGRESS.value,
        )
        season_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            image="http://example.com/s1.jpg",
            season_number=1,
        )
        season = Season.objects.create(
            user=self.user,
            item=season_item,
            related_tv=tv,
            status=Status.IN_PROGRESS.value,
            resume_episode_number=6,
            resume_position_ms=500000,
            resume_duration_ms=1800000,
            resume_updated_at=timezone.now(),
        )

        response = self.client.get(
            reverse(
                "nuvio_player",
                kwargs={
                    "token": self.user.token,
                    "media_type": "series",
                    "video_id": "tt0903747:1:6",
                    "extra": "action=stop&currentTime=1700000&duration=1800000.json",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        season.refresh_from_db()
        self.assertIsNone(season.resume_episode_number)
        self.assertIsNone(season.resume_position_ms)
        self.assertIsNone(season.resume_duration_ms)
        self.assertIsNone(season.resume_updated_at)
        self.assertIsNone(season.resume_bar_percent)
