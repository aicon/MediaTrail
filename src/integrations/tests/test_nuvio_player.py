"""Tests for Nuvio playback received by MediaTrail itself."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import Item, LivePlaybackStatus, MediaTypes, Movie, Sources, Status


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
