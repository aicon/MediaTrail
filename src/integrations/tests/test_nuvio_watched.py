"""Tests for Bearer-auth Nuvio mark-watched / mark-unwatched API."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from integrations.imports import helpers
from integrations.models import NuvioAccount
from integrations import nuvio_outbound


class NuvioWatchedApiTests(TestCase):
    """POST /nuvio/watched.json never puts the token in the URL."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="watched-user",
            password="testpass123",
        )
        self.user.nuvio_sync_mark_played_enabled = True
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(
            update_fields=[
                "nuvio_sync_mark_played_enabled",
                "nuvio_sync_mark_unplayed_enabled",
            ],
        )
        NuvioAccount.objects.create(
            user=self.user,
            email=helpers.encrypt("watched@example.com"),
            password=helpers.encrypt("secret"),
            profile_id=1,
        )
        self.url = reverse("nuvio_watched")

    def _post(self, payload, *, token=None, auth=True):
        headers = {}
        if auth:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token or self.user.token}"
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def test_missing_bearer_is_rejected(self):
        response = self._post(
            {"action": "watched", "type": "movie", "id": "tt0137523"},
            auth=False,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "missing_token")

    def test_invalid_bearer_is_rejected(self):
        response = self._post(
            {"action": "watched", "type": "movie", "id": "tt0137523"},
            token="not-a-real-token",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "invalid_token")

    def test_bad_payload_is_rejected(self):
        response = self._post({"action": "watched", "type": "movie"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "missing_id")

    def test_series_requires_season_and_episode(self):
        response = self._post(
            {"action": "watched", "type": "series", "id": "tt0903747"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "missing_episode")

    @patch("integrations.nuvio_watched.NuvioImporter._apply", return_value=True)
    def test_movie_watched_ok(self, mock_apply):
        response = self._post(
            {
                "action": "watched",
                "type": "movie",
                "id": "tt0137523",
                "watched_at": "2024-01-15T12:00:00Z",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["action"], "watched")
        mock_apply.assert_called_once()
        row = mock_apply.call_args.args[0]
        self.assertEqual(row["content_id"], "tt0137523")
        self.assertEqual(row["content_type"], "movie")
        self.assertEqual(mock_apply.call_args.kwargs["operation"], "upsert")
        self.assertTrue(
            nuvio_outbound.is_pending_outbound(
                self.user.id,
                {"content_id": "tt0137523", "operation": "upsert"},
            ),
        )

    @patch("integrations.nuvio_watched.NuvioImporter._apply", return_value=True)
    def test_episode_unwatched_ok(self, mock_apply):
        response = self._post(
            {
                "action": "unwatched",
                "type": "series",
                "id": "tt0903747",
                "season": 1,
                "episode": 2,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(mock_apply.call_args.kwargs["operation"], "delete")
        row = mock_apply.call_args.args[0]
        self.assertEqual(row["season"], 1)
        self.assertEqual(row["episode"], 2)

    @patch("integrations.nuvio_watched.NuvioImporter._apply")
    def test_mark_played_toggle_off_skips(self, mock_apply):
        self.user.nuvio_sync_mark_played_enabled = False
        self.user.save(update_fields=["nuvio_sync_mark_played_enabled"])
        response = self._post(
            {"action": "watched", "type": "movie", "id": "tt0137523"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "skipped")
        self.assertEqual(response.json()["reason"], "mark_played_disabled")
        mock_apply.assert_not_called()

    @patch("integrations.nuvio_watched.NuvioImporter._apply")
    def test_mark_unplayed_toggle_off_skips(self, mock_apply):
        self.user.nuvio_sync_mark_unplayed_enabled = False
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        response = self._post(
            {"action": "unwatched", "type": "movie", "id": "tt0137523"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "skipped")
        self.assertEqual(response.json()["reason"], "mark_unplayed_disabled")
        mock_apply.assert_not_called()

    @patch("integrations.nuvio_watched.NuvioImporter._apply", return_value=True)
    def test_idempotent_repeat_succeeds(self, mock_apply):
        payload = {"action": "watched", "type": "movie", "id": "tt0137523"}
        first = self._post(payload)
        second = self._post(payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mock_apply.call_count, 2)

    def test_token_never_in_path(self):
        self.assertNotIn(self.user.token, self.url)
        self.assertEqual(self.url, "/nuvio/watched.json")
