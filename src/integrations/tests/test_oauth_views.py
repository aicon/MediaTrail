import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


class TraktResponse:
    """Minimal response for the Trakt device calls."""

    def __init__(self, status_code, payload):
        """Store the status and JSON body. None means an empty body."""
        self.status_code = status_code
        self._payload = payload

    def json(self):
        """Return the JSON body."""
        if self._payload is None:
            msg = "empty"
            raise ValueError(msg)
        return self._payload


class TraktOAuthViewTests(TestCase):
    """Test Trakt OAuth redirect URL handling."""

    def setUp(self):
        """Create user for the tests."""
        credentials = {"username": "testuser", "password": "testpass123"}
        self.user = get_user_model().objects.create_user(**credentials)
        self.client.login(**credentials)

    @override_settings(
        URLS=["https://mediatrail.example.com:8924"],
        TRAKT_API_PKCE="pkce-client-id-1234567890",
    )
    def test_trakt_oauth_uses_auth_host_and_pkce(self):
        """Browser login goes to auth.trakt.tv with S256 PKCE."""
        response = self.client.post(
            reverse("trakt_oauth"),
            {"mode": "new", "frequency": "once", "time": "14:30"},
        )

        self.assertEqual(response.status_code, 302)
        redirect = urlparse(response["Location"])
        query = parse_qs(redirect.query)
        self.assertEqual(redirect.scheme, "https")
        self.assertEqual(redirect.netloc, "auth.trakt.tv")
        self.assertEqual(redirect.path, "/oauth/authorize")
        self.assertEqual(query["client_id"], ["pkce-client-id-1234567890"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertTrue(query["code_challenge"][0])
        self.assertEqual(
            query["redirect_uri"],
            ["https://mediatrail.example.com:8924/import/trakt/private"],
        )

        state = self.client.session[query["state"][0]]
        self.assertEqual(
            state["redirect_uri"],
            "https://mediatrail.example.com:8924/import/trakt/private",
        )
        self.assertTrue(state["code_verifier"])

    @override_settings(TRAKT_API_PKCE="")
    def test_trakt_oauth_requires_pkce_client(self):
        """Browser login stays unavailable until TRAKT_API_PKCE is set."""
        response = self.client.post(
            reverse("trakt_oauth"),
            {"mode": "new", "frequency": "once", "time": "14:30"},
        )
        self.assertRedirects(response, reverse("import_data"))

    @override_settings(URLS=["https://mediatrail.example.com:8924"])
    @patch("integrations.views.tasks.import_trakt.delay")
    @patch("integrations.views.trakt.handle_oauth_callback")
    def test_trakt_callback_reuses_stored_redirect_uri(
        self,
        mock_oauth_callback,
        mock_import_trakt,
    ):
        """Token exchange and import reuse the original redirect URI and PKCE verifier."""
        redirect_uri = "https://mediatrail.example.com:8924/import/trakt/private"
        session = self.client.session
        session["state-token"] = {
            "mode": "new",
            "frequency": "once",
            "time": "14:30",
            "redirect_uri": redirect_uri,
            "code_verifier": "verifier-value",
        }
        session.save()
        mock_oauth_callback.return_value = {
            "refresh_token": "refresh-token",
            "username": "trakt-user",
        }

        response = self.client.get(
            reverse("import_trakt_private"),
            {"code": "code", "state": "state-token"},
        )

        self.assertRedirects(response, reverse("import_data"))
        mock_oauth_callback.assert_called_once()
        self.assertEqual(
            mock_oauth_callback.call_args.kwargs["redirect_uri"],
            redirect_uri,
        )
        self.assertEqual(
            mock_oauth_callback.call_args.kwargs["code_verifier"],
            "verifier-value",
        )
        mock_import_trakt.assert_called_once()
        self.assertEqual(mock_import_trakt.call_args.kwargs["auth"], "pkce")
        self.assertEqual(
            mock_import_trakt.call_args.kwargs["redirect_uri"],
            redirect_uri,
        )
        self.assertNotIn("state-token", self.client.session)

    @patch("integrations.views.trakt.handle_oauth_callback")
    def test_trakt_callback_rejects_missing_state(self, mock_oauth_callback):
        """Missing OAuth state is handled without a server error."""
        response = self.client.get(
            reverse("import_trakt_private"),
            {"code": "code"},
        )

        self.assertRedirects(response, reverse("import_data"))
        mock_oauth_callback.assert_not_called()

    @patch("integrations.views.trakt.handle_oauth_callback")
    def test_trakt_callback_rejects_state_mismatch(self, mock_oauth_callback):
        """Unknown state token aborts before the code exchange."""
        response = self.client.get(
            reverse("import_trakt_private"),
            {"code": "code", "state": "not-in-session"},
        )

        self.assertRedirects(response, reverse("import_data"))
        mock_oauth_callback.assert_not_called()

    @override_settings(TRAKT_API_PKCE="")
    def test_device_start_requires_the_new_client_id(self):
        """The new API stays unavailable until TRAKT_API_PKCE is set."""
        response = self.client.post(
            reverse("trakt_device_start"),
            {"mode": "new", "frequency": "once", "time": "14:30"},
        )

        self.assertRedirects(response, reverse("import_data"))

    @override_settings(TRAKT_API_PKCE="pkce-client-id-1234567890")
    @patch("integrations.imports.trakt._post_trakt")
    def test_device_start_shows_the_user_code_only(self, mock_post):
        """The page shows the short code and keeps the device code in the session."""
        mock_post.return_value = TraktResponse(
            200,
            {
                "device_code": "secret-device-code",
                "user_code": "AB12CD34",
                "verification_url": "https://trakt.tv/activate",
                "expires_in": 600,
                "interval": 5,
            },
        )

        response = self.client.post(
            reverse("trakt_device_start"),
            {"mode": "new", "frequency": "once", "time": "14:30"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AB12CD34")
        self.assertNotContains(response, "secret-device-code")
        self.assertEqual(
            self.client.session["trakt_device"]["device_code"],
            "secret-device-code",
        )
        self.assertEqual(
            mock_post.call_args.args[1],
            {"client_id": "pkce-client-id-1234567890"},
        )

    @override_settings(TRAKT_API_PKCE="pkce-client-id-1234567890")
    @patch("integrations.imports.trakt._post_trakt")
    def test_device_poll_keeps_waiting_on_an_empty_pending_response(self, mock_post):
        """An empty HTTP 400 is still waiting, and the code stays available."""
        session = self.client.session
        session["trakt_device"] = {
            "device_code": "secret-device-code",
            "interval": 5,
            "expires_at": time.time() + 600,
            "mode": "new",
            "frequency": "once",
            "time": "14:30",
        }
        session.save()
        mock_post.return_value = TraktResponse(400, None)

        response = self.client.post(reverse("trakt_device_poll"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")
        self.assertIn("trakt_device", self.client.session)
        self.assertEqual(
            mock_post.call_args.args[1],
            {"code": "secret-device-code", "client_id": "pkce-client-id-1234567890"},
        )

    @override_settings(TRAKT_API_PKCE="pkce-client-id-1234567890")
    @patch("integrations.imports.trakt._post_trakt")
    def test_device_poll_keeps_the_code_when_trakt_returns_404(self, mock_post):
        """A not-found token check is still waiting, and the code stays usable."""
        session = self.client.session
        session["trakt_device"] = {
            "device_code": "secret-device-code",
            "interval": 5,
            "expires_at": time.time() + 600,
            "mode": "new",
            "frequency": "once",
            "time": "14:30",
        }
        session.save()
        mock_post.return_value = TraktResponse(404, None)

        response = self.client.post(reverse("trakt_device_poll"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pending")
        self.assertIn("trakt_device", self.client.session)

    @override_settings(TRAKT_API_PKCE="pkce-client-id-1234567890")
    @patch("integrations.views.tasks.import_trakt.delay")
    @patch(
        "integrations.views.trakt.get_username_from_oauth",
        return_value="trakt-user",
    )
    @patch("integrations.imports.trakt._post_trakt")
    def test_device_poll_queues_with_the_time_chosen_earlier(
        self,
        mock_post,
        _username,
        mock_import,
    ):
        """Approval saves the connection and queues the time already chosen."""
        session = self.client.session
        session["trakt_device"] = {
            "device_code": "secret-device-code",
            "interval": 5,
            "expires_at": time.time() + 600,
            "mode": "overwrite",
            "frequency": "once",
            "time": "14:30",
        }
        session.save()
        mock_post.return_value = TraktResponse(
            200,
            {"access_token": "access", "refresh_token": "refresh"},
        )

        response = self.client.post(reverse("trakt_device_poll"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect"], reverse("import_data"))
        self.assertNotIn("trakt_device", self.client.session)
        self.assertEqual(mock_import.call_args.kwargs["auth"], "device")
        self.assertEqual(mock_import.call_args.kwargs["username"], "trakt-user")

    @override_settings(TRAKT_API_PKCE="pkce-client-id-1234567890")
    @patch("integrations.views.helpers.create_import_schedule")
    @patch(
        "integrations.views.trakt.get_username_from_oauth",
        return_value="trakt-user",
    )
    @patch("integrations.imports.trakt._post_trakt")
    def test_device_poll_keeps_a_recurring_start_time(
        self,
        mock_post,
        _username,
        mock_schedule,
    ):
        """A recurring import keeps the start time chosen before sign-in."""
        session = self.client.session
        session["trakt_device"] = {
            "device_code": "secret-device-code",
            "interval": 5,
            "expires_at": time.time() + 600,
            "mode": "new",
            "frequency": "daily",
            "time": "08:15",
        }
        session.save()
        mock_post.return_value = TraktResponse(
            200,
            {"access_token": "access", "refresh_token": "refresh"},
        )

        response = self.client.post(reverse("trakt_device_poll"))

        self.assertEqual(response.json()["redirect"], reverse("import_data"))
        self.assertEqual(mock_schedule.call_args.args[3], "daily")
        self.assertEqual(mock_schedule.call_args.args[4], "08:15")
        self.assertEqual(
            mock_schedule.call_args.kwargs["task_kwargs"]["auth"],
            "device",
        )
