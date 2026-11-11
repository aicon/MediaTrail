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
    def test_manifest_has_no_token_and_includes_the_logo(self):
        """The installed manifest is public and points at the addon logo."""
        response = self.client.get(reverse("nuvio_manifest"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.request["PATH_INFO"].endswith("/nuvio/manifest.json"))
        body = response.json()
        self.assertEqual(body["resources"], ["player"])
        self.assertEqual(
            body["logo"],
            "https://mediatrail.example/static/nuvio/logo.png",
        )
        self.assertNotIn(self.user.token, response.request["PATH_INFO"])

    @patch("integrations.nuvio_player.upsert_live_playback")
    @patch(
        "integrations.nuvio_player.tmdb.find",
        return_value={"movie_results": [{"id": 550}], "tv_results": []},
    )
    def test_progress_updates_now_watching(self, _find, mock_upsert):
        """A progress event writes the live playback row."""
        response = self.client.get(
            reverse(
                "nuvio_player",
                args=[
                    "movie",
                    "tt0137523",
                    "action=progress&currentTime=12000&duration=1800000.json",
                ],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mock_upsert.call_args.kwargs["media_id"],
            "550",
        )
        self.assertEqual(mock_upsert.call_args.kwargs["position_ms"], 12000)
        self.assertEqual(
            mock_upsert.call_args.kwargs["status"],
            LivePlaybackStatus.WATCHING,
        )
