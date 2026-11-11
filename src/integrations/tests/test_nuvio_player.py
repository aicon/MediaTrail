"""Tests for Nuvio playback received by MediaTrail itself."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import LivePlaybackStatus


class NuvioPlayerTests(TestCase):
    """Player events update Now Watching without a separate scrobbler."""

    def setUp(self):
        """Create the user whose token is in the addon address."""
        self.user = get_user_model().objects.create_user(
            username="nuvio-user",
            password="testpass123",
        )

    def test_manifest_uses_the_user_token(self):
        """The installed manifest is served by this MediaTrail."""
        response = self.client.get(
            reverse("nuvio_manifest", args=[self.user.token]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resources"], ["player"])

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
                    self.user.token,
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
