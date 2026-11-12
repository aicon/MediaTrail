"""Tests for Nuvio playback received by MediaTrail itself."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import LivePlaybackStatus


class NuvioPlayerTests(TestCase):
    """Player events update Now Watching without a separate scrobbler."""

    def setUp(self):
        """Create the account that receives Nuvio playback."""
        self.user = get_user_model().objects.create_user(
            username="nuvio-user",
            password="testpass123",
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
