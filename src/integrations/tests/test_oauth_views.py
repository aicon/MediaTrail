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

    @override_settings(TRAKT_API_PKCE="pkce-client-id-1234567890")
    @patch("integrations.imports.trakt._post_trakt")
    def test_trakt_oauth_alias_starts_new_api_code_login(self, mock_post):
        """Private login URL aliases to the working activate-code flow."""
        mock_post.return_value = TraktResponse(
            200,
            {
                "device_code": "secret-device-code",
                "user_code": "ABCD-1234",
                "verification_url": "https://trakt.tv/activate",
                "expires_in": 600,
                "interval": 5,
            },
        )
        response = self.client.post(
            reverse("trakt_oauth"),
            {"mode": "new", "frequency": "once", "time": "14:30"},
        )
        self.assertRedirects(response, reverse("trakt_device_start"))
        self.assertEqual(
            self.client.session["trakt_device"]["device_code"],
            "secret-device-code",
        )

    @override_settings(TRAKT_API_PKCE="")
    def test_trakt_oauth_requires_pkce_client(self):
        """New API login stays unavailable until TRAKT_API_PKCE is set."""
        response = self.client.post(
            reverse("trakt_oauth"),
            {"mode": "new", "frequency": "once", "time": "14:30"},
        )
        self.assertRedirects(response, reverse("import_data"))

    @patch("integrations.views.trakt.handle_oauth_callback")
    def test_trakt_callback_rejects_legacy_browser_return(self, mock_oauth_callback):
        """Stray authorize callbacks do not attempt a broken token exchange."""
        response = self.client.get(
            reverse("import_trakt_private"),
            {"code": "code", "state": "state-token"},
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


class SimklOAuthViewTests(TestCase):
    """Test Simkl OAuth V1 fallback and AUTH V2 + PKCE."""

    def setUp(self):
        """Create user for the tests."""
        credentials = {"username": "testuser", "password": "testpass123"}
        self.user = get_user_model().objects.create_user(**credentials)
        self.client.login(**credentials)

    @override_settings(
        URLS=["https://mediatrail.example.com:8924"],
        SIMKL_V2_ID="",
        SIMKL_ID="v1-client-id",
    )
    def test_simkl_oauth_falls_back_to_v1_without_v2_id(self):
        """Without SIMKL_V2_ID, new links still use AUTH V1 authorize."""
        response = self.client.post(
            reverse("simkl_oauth"),
            {"mode": "new", "frequency": "once", "time": "14:30"},
        )

        self.assertEqual(response.status_code, 302)
        redirect = urlparse(response["Location"])
        query = parse_qs(redirect.query)
        self.assertEqual(redirect.netloc, "simkl.com")
        self.assertEqual(redirect.path, "/oauth/authorize")
        self.assertEqual(query["client_id"], ["v1-client-id"])
        self.assertNotIn("code_challenge", query)
        state = self.client.session[query["state"][0]]
        self.assertEqual(state["auth"], "v1")

    @override_settings(
        URLS=["https://mediatrail.example.com:8924"],
        SIMKL_V2_ID="v2-client-id-abc",
    )
    def test_simkl_oauth_uses_v2_authorize_and_pkce(self):
        """With SIMKL_V2_ID, new links use oauth2 authorize and S256 PKCE."""
        response = self.client.post(
            reverse("simkl_oauth"),
            {"mode": "new", "frequency": "once", "time": "14:30"},
        )

        self.assertEqual(response.status_code, 302)
        redirect = urlparse(response["Location"])
        query = parse_qs(redirect.query)
        self.assertEqual(redirect.netloc, "simkl.com")
        self.assertEqual(redirect.path, "/oauth2/authorize")
        self.assertEqual(query["client_id"], ["v2-client-id-abc"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertTrue(query["code_challenge"][0])
        self.assertEqual(query["scope"], ["media:read media:write"])
        self.assertEqual(
            query["redirect_uri"],
            ["https://mediatrail.example.com:8924/import/simkl_private"],
        )
        state = self.client.session[query["state"][0]]
        self.assertEqual(state["auth"], "v2")
        self.assertTrue(state["code_verifier"])

    @override_settings(SIMKL_V2_ID="v2-client-id-abc")
    @patch("integrations.views.tasks.import_simkl.delay")
    @patch("integrations.views.simkl.get_token")
    def test_simkl_v2_callback_stores_refresh_token(
        self,
        mock_get_token,
        mock_import_simkl,
    ):
        """V2 callback encrypts the refresh token and queues auth=v2."""
        session = self.client.session
        session["state-token"] = {
            "mode": "new",
            "frequency": "once",
            "time": "14:30",
            "redirect_uri": "https://mediatrail.example.com/import/simkl_private",
            "code_verifier": "verifier-value",
            "auth": "v2",
        }
        session.save()
        mock_get_token.return_value = {
            "access_token": "access",
            "refresh_token": "refresh-token",
            "username": "simkl-user",
            "auth": "v2",
        }

        response = self.client.get(
            reverse("import_simkl_private"),
            {
                "code": "auth-code",
                "state": "state-token",
                "iss": "https://simkl.com",
            },
        )

        self.assertRedirects(response, reverse("import_data"))
        mock_get_token.assert_called_once()
        self.assertEqual(
            mock_get_token.call_args.kwargs["code_verifier"],
            "verifier-value",
        )
        self.assertEqual(mock_get_token.call_args.kwargs["auth"], "v2")
        mock_import_simkl.assert_called_once()
        self.assertEqual(mock_import_simkl.call_args.kwargs["auth"], "v2")
        self.assertNotIn("state-token", self.client.session)

    @override_settings(SIMKL_V2_ID="v2-client-id-abc")
    @patch("integrations.views.simkl.get_token")
    def test_simkl_v2_callback_rejects_bad_issuer(self, mock_get_token):
        """V2 callback rejects a mismatched iss before exchanging the code."""
        session = self.client.session
        session["state-token"] = {
            "mode": "new",
            "frequency": "once",
            "time": "14:30",
            "code_verifier": "verifier-value",
            "auth": "v2",
        }
        session.save()

        response = self.client.get(
            reverse("import_simkl_private"),
            {
                "code": "auth-code",
                "state": "state-token",
                "iss": "https://evil.example",
            },
        )

        self.assertRedirects(response, reverse("import_data"))
        mock_get_token.assert_not_called()

    @patch("integrations.views.simkl.get_token")
    def test_simkl_callback_rejects_missing_state(self, mock_get_token):
        """Missing OAuth state aborts without exchanging the code."""
        response = self.client.get(
            reverse("import_simkl_private"),
            {"code": "auth-code"},
        )

        self.assertRedirects(response, reverse("import_data"))
        mock_get_token.assert_not_called()

    @override_settings(SIMKL_V2_ID="")
    @patch("app.providers.services.api_request")
    def test_simkl_v1_callback_missing_code_is_controlled(self, mock_api_request):
        """V1 callback without code redirects with a message, not HTTP 500."""
        session = self.client.session
        session["state-token"] = {
            "mode": "new",
            "frequency": "once",
            "time": "14:30",
            "auth": "v1",
        }
        session.save()

        response = self.client.get(
            reverse("import_simkl_private"),
            {"state": "state-token"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        mock_api_request.assert_not_called()
        self.assertContains(response, "Simkl authorization failed.")

    @override_settings(SIMKL_V2_ID="v2-client-id-abc")
    @patch("integrations.imports.simkl.get_token_v1")
    @patch("integrations.imports.simkl.exchange_v2_code")
    def test_simkl_v2_missing_code_does_not_use_v1(
        self,
        mock_exchange_v2,
        mock_get_token_v1,
    ):
        """V2 session without code fails closed and never calls V1 exchange."""
        from django.test import RequestFactory

        from integrations.imports import helpers, simkl

        mock_exchange_v2.side_effect = helpers.MediaImportError(
            "Invalid or expired Simkl authorization request.",
        )
        request = RequestFactory().get(
            reverse("import_simkl_private"),
            {"iss": "https://simkl.com"},
        )
        with self.assertRaises(helpers.MediaImportError):
            simkl.get_token(
                request,
                code_verifier="verifier-value",
                redirect_uri="https://example.com/import/simkl_private",
                auth="v2",
            )
        mock_exchange_v2.assert_called_once_with(
            None,
            "https://example.com/import/simkl_private",
            "verifier-value",
        )
        mock_get_token_v1.assert_not_called()

    @override_settings(SIMKL_V2_ID="v2-client-id-abc")
    @patch("integrations.imports.simkl.get_token_v1")
    @patch("integrations.imports.simkl.exchange_v2_code")
    def test_simkl_v2_missing_verifier_does_not_use_v1(
        self,
        mock_exchange_v2,
        mock_get_token_v1,
    ):
        """V2 session without PKCE verifier fails closed (no V1 fallback)."""
        from django.test import RequestFactory

        from integrations.imports import helpers, simkl

        request = RequestFactory().get(
            reverse("import_simkl_private"),
            {"code": "auth-code", "iss": "https://simkl.com"},
        )
        with self.assertRaises(helpers.MediaImportError) as raised:
            simkl.get_token(
                request,
                code_verifier=None,
                redirect_uri="https://example.com/import/simkl_private",
                auth="v2",
            )
        self.assertIn("invalid or expired", str(raised.exception).lower())
        mock_exchange_v2.assert_not_called()
        mock_get_token_v1.assert_not_called()

    @override_settings(SIMKL_V2_ID="")
    @patch("integrations.views.tasks.import_simkl.delay")
    @patch("integrations.views.simkl.get_token")
    def test_simkl_v1_callback_passes_auth_v1(
        self,
        mock_get_token,
        mock_import_simkl,
    ):
        """V1 session still uses the V1 token-exchange path via auth=v1."""
        session = self.client.session
        session["state-token"] = {
            "mode": "new",
            "frequency": "once",
            "time": "14:30",
            "auth": "v1",
        }
        session.save()
        mock_get_token.return_value = {
            "access_token": "access",
            "username": "simkl-user",
            "auth": "v1",
        }

        response = self.client.get(
            reverse("import_simkl_private"),
            {"code": "auth-code", "state": "state-token"},
        )

        self.assertRedirects(response, reverse("import_data"))
        mock_get_token.assert_called_once()
        self.assertEqual(mock_get_token.call_args.kwargs["auth"], "v1")
        mock_import_simkl.assert_called_once()
        self.assertEqual(mock_import_simkl.call_args.kwargs["auth"], "v1")

