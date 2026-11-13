"""Contains views for importing and exporting media data from various sources."""

import json
import logging
import re
import secrets
import time
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

import users
from app import helpers as app_helpers
from integrations import exports, nuvio_player as nuvio_addon, tasks
from integrations import nuvio_watched as nuvio_watched_api
from integrations.imports import anilist, helpers, nuvio, simkl, trakt
from integrations.webhooks import emby, jellyfin, plex

logger = logging.getLogger(__name__)


@require_POST
def import_nuvio(request):
    """Save encrypted Nuvio credentials and queue or schedule the import."""
    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    email, password = nuvio.fill_saved_login(request.user, email, password)
    profile_raw = (request.POST.get("profile_id") or "1").strip()
    if not email or not password:
        messages.error(request, _("Nuvio email and password are required."))
        return redirect("import_data")
    if not profile_raw.isdigit() or int(profile_raw) < 1:
        messages.error(request, _("Nuvio profile must be a positive number."))
        return redirect("import_data")

    nuvio.save_account(request.user, email, password, int(profile_raw))
    mode = request.POST.get("mode", "new")
    frequency = request.POST.get("frequency", "once")
    if frequency == "once":
        tasks.import_nuvio.delay(
            user_id=request.user.id,
            mode=mode,
            username=email,
        )
        messages.info(
            request,
            _("The task to import media from Nuvio has been queued."),
        )
    else:
        helpers.create_import_schedule(
            email,
            request,
            mode,
            frequency,
            request.POST.get("time", ""),
            "Nuvio",
        )
    return redirect("import_data")


@require_POST
def trakt_oauth(request):
    """Private Trakt login entry point.

    Browser authorize on auth.trakt.tv is unreliable with modern secret-less
    apps; the working new-API path is the activate code. Keep this URL as an
    alias so older forms still reach that flow.
    """
    return trakt_device_start(request)


@require_GET
def import_trakt_private(request):
    """Legacy browser-OAuth callback URL.

    New private links use the activate-code flow. A stray callback is rejected
    instead of attempting the broken authorize exchange.
    """
    messages.error(
        request,
        _(
            "Use Connect with the new Trakt API and enter the code at "
            "trakt.tv/activate."
        ),
    )
    return redirect("import_data")


def _queue_trakt_import(request, username, refresh_token, state, auth):
    """Queue or schedule a private Trakt import."""
    enc_token = helpers.encrypt(refresh_token)
    frequency = state["frequency"]
    mode = state["mode"]
    import_time = state["time"]
    task_kwargs = {}
    redirect_uri = state.get("redirect_uri")
    if redirect_uri:
        task_kwargs["redirect_uri"] = redirect_uri
    if auth != "legacy":
        task_kwargs["auth"] = auth

    if frequency == "once":
        tasks.import_trakt.delay(
            token=enc_token,
            user_id=request.user.id,
            mode=mode,
            username=username,
            redirect_uri=redirect_uri,
            auth=auth,
        )
        messages.info(request, "The task to import media from Trakt has been queued.")
    else:
        helpers.create_import_schedule(
            username,
            request,
            mode,
            frequency,
            import_time,
            "Trakt",
            token=enc_token,
            task_kwargs=task_kwargs or None,
        )


@require_http_methods(["GET", "POST"])
def trakt_device_start(request):
    """Start a device sign-in, then keep the code page refreshable."""
    if request.method == "GET":
        return _render_trakt_device_wait(request)

    if not trakt.device_client_id():
        messages.error(request, "The new Trakt API is not configured on this server.")
        return redirect("import_data")

    try:
        started = trakt.start_device_login()
    except helpers.MediaImportError as error:
        messages.error(request, str(error))
        return redirect("import_data")

    request.session["trakt_device"] = {
        "device_code": started["device_code"],
        "user_code": started["user_code"],
        "verification_url": started["verification_url"],
        "interval": started["interval"],
        "expires_at": time.time() + started["expires_in"],
        "mode": request.POST.get("mode", "new"),
        "frequency": request.POST.get("frequency", "once"),
        "time": request.POST.get("time", ""),
    }
    return redirect("trakt_device_start")


def _render_trakt_device_wait(request):
    """Show the device code and keep polling after the user comes back."""
    entry = request.session.get("trakt_device")
    if not entry or time.time() > float(entry.get("expires_at") or 0):
        request.session.pop("trakt_device", None)
        messages.error(request, "The Trakt code expired. Start again.")
        return redirect("import_data")

    return render(
        request,
        "integrations/trakt_device.html",
        {
            "user_code": entry.get("user_code") or "",
            "verification_url": entry.get("verification_url")
            or "https://trakt.tv/activate",
            "interval": entry.get("interval") or 5,
        },
    )


@require_POST
def trakt_device_poll(request):
    """Poll Trakt until the device code is approved."""
    entry = request.session.get("trakt_device")
    if not entry or time.time() > float(entry.get("expires_at") or 0):
        request.session.pop("trakt_device", None)
        return JsonResponse(
            {"status": "error", "error": "The Trakt code expired. Start again."},
            status=400,
        )

    result = trakt.poll_device_login(entry["device_code"])
    if result["status"] == "pending":
        return JsonResponse(
            {"status": "pending", "interval": entry.get("interval") or 5},
        )
    if result["status"] != "approved":
        request.session.pop("trakt_device", None)
        return JsonResponse(
            {
                "status": "error",
                "error": result.get("message") or "Trakt rejected the device sign-in.",
            },
            status=400,
        )

    token = result["token"]
    username = ""
    try:
        username = trakt.get_username_from_oauth(
            token["access_token"],
            client_id=trakt.device_client_id(),
        )
    except (helpers.MediaImportError, requests.RequestException):
        logger.exception("Trakt username lookup failed after device approval")

    request.session.pop("trakt_device", None)
    _queue_trakt_import(
        request,
        username=username,
        refresh_token=token["refresh_token"],
        state={
            "mode": entry.get("mode") or "new",
            "frequency": entry.get("frequency") or "once",
            "time": entry.get("time") or "",
        },
        auth="device",
    )
    return JsonResponse(
        {"status": "ok", "redirect": reverse("import_data")},
    )


@require_POST
def import_trakt_public(request):
    """View for importing Trakt data using public username."""
    username = request.POST.get("user")
    if not username:
        messages.error(request, "Trakt username is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]
    import_time = request.POST["time"]

    if frequency == "once":
        tasks.import_trakt.delay(
            user_id=request.user.id,
            mode=mode,
            username=username,
        )
        messages.info(request, "The task to import media from Trakt has been queued.")
    else:
        helpers.create_import_schedule(
            username=username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="Trakt",
        )
    return redirect("import_data")


@require_POST
def import_trakt_export(request):
    """Import from a Trakt website export ZIP after fail-closed validation."""
    upload = request.FILES.get("trakt_export_zip")
    if not upload:
        messages.error(request, "A Trakt export ZIP file is required.")
        return redirect("import_data")

    mode = request.POST.get("mode", "new")
    try:
        preview = trakt.inspect_trakt_export(upload)
    except helpers.MediaImportError as error:
        messages.error(request, str(error))
        return redirect("import_data")

    if hasattr(upload, "seek"):
        upload.seek(0)

    counts = preview["counts"]
    tasks.import_trakt.delay(
        user_id=request.user.id,
        mode=mode,
        file=upload,
    )
    messages.info(
        request,
        _(
            "Trakt ZIP import queued for %(user)s "
            "(history %(history)s, watchlist %(watchlist)s, "
            "ratings %(ratings)s, comments %(comments)s). "
            "Mode “%(mode)s”: new skips titles you already have; "
            "overwrite replaces matching Trakt rows."
        )
        % {
            "user": preview["username"],
            "history": counts["history"],
            "watchlist": counts["watchlist"],
            "ratings": counts["ratings"],
            "comments": counts["comments"],
            "mode": mode,
        },
    )
    return redirect("import_data")


@require_POST
def simkl_oauth(request):
    """Start Simkl OAuth: AUTH V2 + PKCE when configured, else legacy V1."""
    redirect_uri = app_helpers.build_absolute_app_url(
        request,
        reverse("import_simkl_private"),
    )
    state = {
        "mode": request.POST["mode"],
        "frequency": request.POST["frequency"],
        "time": request.POST["time"],
        "redirect_uri": redirect_uri,
    }

    if simkl.v2_enabled():
        code_verifier, code_challenge = simkl.make_pkce_pair()
        state["code_verifier"] = code_verifier
        state["auth"] = "v2"
        state_token = secrets.token_urlsafe(32)
        request.session[state_token] = state
        return redirect(
            f"{simkl.SIMKL_AUTHORIZE_URL}?{
                urlencode(
                    {
                        'client_id': simkl.v2_client_id(),
                        'redirect_uri': redirect_uri,
                        'response_type': 'code',
                        'scope': 'media:read media:write',
                        'state': state_token,
                        'code_challenge': code_challenge,
                        'code_challenge_method': 'S256',
                    }
                )
            }",
        )

    # Legacy AUTH V1 (deprecated; planned retirement ~April 2027).
    state["auth"] = "v1"
    state_token = secrets.token_urlsafe(32)
    request.session[state_token] = state
    return redirect(
        f"{simkl.SIMKL_V1_AUTHORIZE_URL}?{
            urlencode(
                {
                    'client_id': settings.SIMKL_ID,
                    'redirect_uri': redirect_uri,
                    'response_type': 'code',
                    'state': state_token,
                }
            )
        }",
    )


@require_GET
def import_simkl_private(request):
    """Handle Simkl OAuth callback and queue/schedule the import."""
    state_token = request.GET.get("state")
    state = request.session.pop(state_token, None) if state_token else None
    if not state:
        messages.error(request, "Invalid or expired Simkl authorization request.")
        return redirect("import_data")

    code_verifier = state.pop("code_verifier", None)
    if request.GET.get("error"):
        messages.error(request, "Simkl authorization was cancelled or failed.")
        return redirect("import_data")

    if state.get("auth") == "v2":
        iss = request.GET.get("iss")
        if iss != simkl.SIMKL_ISSUER:
            messages.error(request, "Simkl authorization response was rejected.")
            return redirect("import_data")

    redirect_uri = state.get("redirect_uri")
    session_auth = state.get("auth") or "v1"
    try:
        oauth_callback = simkl.get_token(
            request,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            auth=session_auth,
        )
    except helpers.MediaImportError as error:
        messages.error(request, str(error))
        return redirect("import_data")

    auth = oauth_callback.get("auth") or session_auth
    if auth == "v2":
        enc_token = helpers.encrypt(oauth_callback["refresh_token"])
    else:
        enc_token = helpers.encrypt(oauth_callback["access_token"])

    frequency = state["frequency"]
    mode = state["mode"]
    import_time = state["time"]

    if frequency == "once":
        tasks.import_simkl.delay(
            token=enc_token,
            user_id=request.user.id,
            mode=mode,
            auth=auth,
        )
        messages.info(request, "The task to import media from Simkl has been queued.")
    else:
        task_kwargs = {"auth": auth} if auth != "v1" else None
        helpers.create_import_schedule(
            oauth_callback["username"],
            request,
            mode,
            frequency,
            import_time,
            "SIMKL",
            token=enc_token,
            task_kwargs=task_kwargs,
        )
        if auth == "v1":
            messages.warning(
                request,
                _(
                    "Simkl AUTH V1 is deprecated and planned for retirement around "
                    "April 2027. Configure SIMKL_V2_ID and reconnect when ready."
                ),
            )

    return redirect("import_data")


@require_POST
def import_mal(request):
    """View for importing anime and manga data from MyAnimeList."""
    username = request.POST.get("user")
    if not username:
        messages.error(request, "MyAnimeList username is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]

    if frequency == "once":
        tasks.import_mal.delay(username=username, user_id=request.user.id, mode=mode)
        messages.info(
            request,
            "The task to import media from MyAnimeList has been queued.",
        )
    else:
        import_time = request.POST["time"]
        helpers.create_import_schedule(
            username,
            request,
            mode,
            frequency,
            import_time,
            "MyAnimeList",
        )
    return redirect("import_data")


@require_POST
def anilist_oauth(request):
    """Initiate AniList OAuth flow."""
    redirect_uri = app_helpers.build_absolute_app_url(
        request,
        reverse("import_anilist_private"),
    )
    url = "https://anilist.co/api/v2/oauth/authorize"
    state = {
        "mode": request.POST["mode"],
        "frequency": request.POST["frequency"],
        "time": request.POST["time"],
    }

    state_token = secrets.token_urlsafe(32)
    request.session[state_token] = state

    return redirect(
        f"{url}?{
            urlencode(
                {
                    'client_id': settings.ANILIST_ID,
                    'redirect_uri': redirect_uri,
                    'response_type': 'code',
                    'state': state_token,
                }
            )
        }",
    )


@require_GET
def import_anilist_private(request):
    """View for getting the AniList OAuth2 token."""
    oauth_callback = anilist.get_token(request)
    enc_token = helpers.encrypt(oauth_callback["access_token"])
    state_token = request.GET["state"]
    username = oauth_callback["username"]

    if not username:
        messages.error(request, "AniList username is required.")
        return redirect("import_data")

    frequency = request.session[state_token]["frequency"]
    mode = request.session[state_token]["mode"]
    import_time = request.session[state_token]["time"]

    if frequency == "once":
        tasks.import_anilist.delay(
            user_id=request.user.id,
            mode=mode,
            username=username,
            token=enc_token,
        )
        messages.info(request, "AniList import queued.")
    else:
        helpers.create_import_schedule(
            username=username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="AniList",
            token=enc_token,
        )
    return redirect("import_data")


@require_POST
def import_anilist_public(request):
    """View for importing anime and manga data from AniList."""
    username = request.POST.get("user")
    if not username:
        messages.error(request, "AniList username is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]
    import_time = request.POST["time"]

    if frequency == "once":
        tasks.import_anilist.delay(
            user_id=request.user.id,
            mode=mode,
            username=username,
        )
        messages.info(request, "AniList import queued.")
    else:
        helpers.create_import_schedule(
            username=username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="AniList",
        )
    return redirect("import_data")


@require_POST
def import_kitsu(request):
    """View for importing anime and manga data from Kitsu by user ID."""
    kitsu_id = request.POST.get("user")
    if not kitsu_id:
        messages.error(request, "Kitsu user ID is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]

    if frequency == "once":
        tasks.import_kitsu.delay(username=kitsu_id, user_id=request.user.id, mode=mode)
        messages.info(request, "The task to import media from Kitsu has been queued.")
    else:
        import_time = request.POST["time"]
        helpers.create_import_schedule(
            kitsu_id,
            request,
            mode,
            frequency,
            import_time,
            "Kitsu",
        )
    return redirect("import_data")


@require_POST
def import_yamtrack(request):
    """View for importing a MediaTrail CSV backup."""
    file = request.FILES.get("mediatrail_csv")

    if not file:
        messages.error(request, "MediaTrail CSV file is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    tasks.import_yamtrack.delay(
        file=request.FILES["mediatrail_csv"],
        user_id=request.user.id,
        mode=mode,
    )
    messages.info(
        request,
        "The task to import media from a MediaTrail CSV file has been queued.",
    )
    return redirect("import_data")


@require_POST
def import_hltb(request):
    """View for importing game date from HowLongToBeat."""
    file = request.FILES.get("hltb_csv")

    if not file:
        messages.error(request, "HowLongToBeat CSV file is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    tasks.import_hltb.delay(
        file=request.FILES["hltb_csv"],
        user_id=request.user.id,
        mode=mode,
    )
    messages.info(
        request,
        "The task to import media from HowLongToBeat CSV file has been queued.",
    )
    return redirect("import_data")


@require_POST
def import_steam(request):
    """View for importing game data from Steam."""
    steam_id = request.POST.get("user")
    if not steam_id:
        messages.error(request, "Steam ID is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]

    if frequency == "once":
        tasks.import_steam.delay(username=steam_id, user_id=request.user.id, mode=mode)
        messages.info(request, "The task to import media from Steam has been queued.")
    else:
        import_time = request.POST["time"]
        helpers.create_import_schedule(
            steam_id,
            request,
            mode,
            frequency,
            import_time,
            "Steam",
        )
    return redirect("import_data")


def import_imdb(request):
    """View for importing data from IMDB."""
    file = request.FILES.get("imdb_csv")

    if not file:
        messages.error(request, "IMDB CSV file is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    tasks.import_imdb.delay(
        file=request.FILES["imdb_csv"],
        user_id=request.user.id,
        mode=mode,
    )
    messages.info(
        request,
        "The task to import media from IMDB CSV file has been queued.",
    )
    return redirect("import_data")


@require_POST
def import_goodreads(request):
    """View for importing books data from GoodReads CSV."""
    file = request.FILES.get("goodreads_csv")

    if not file:
        messages.error(request, "GoodReads CSV file is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    tasks.import_goodreads.delay(
        file=request.FILES["goodreads_csv"],
        user_id=request.user.id,
        mode=mode,
    )
    messages.info(
        request,
        "The task to import media from GoodReads CSV file has been queued.",
    )
    return redirect("import_data")


@require_GET
def export_csv(request):
    """View for exporting all media data to a CSV file."""
    now = timezone.localtime()
    response = StreamingHttpResponse(
        streaming_content=exports.generate_rows(request.user),
        content_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="mediatrail_{now}.csv"'},
    )
    logger.info("User %s started CSV export", request.user.username)
    return response


def _nuvio_cors(response, *, methods="GET, OPTIONS"):
    """Allow the Nuvio app to call the addon routes."""
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = methods
    response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


def _nuvio_bearer_token(request):
    """Read Authorization: Bearer <token>. Token must never appear in the URL."""
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _nuvio_public_logo():
    """Absolute logo URL from the configured public origin."""
    try:
        urls = getattr(settings, "URLS", None) or []
    except Exception:  # noqa: BLE001
        return ""
    origin = ""
    for url in urls:
        if url:
            origin = str(url).rstrip("/")
            break
    if origin.startswith(("http://", "https://")):
        return f"{origin}/static/nuvio/logo.png"
    return ""


def _nuvio_manifest_body(user=None):
    """JSON manifest. A logo problem must not turn the addon into an error page."""
    catalogs = []
    if user is not None:
        try:
            from integrations.nuvio_library import catalog_manifest_entries

            catalogs = catalog_manifest_entries(user)
        except Exception:  # noqa: BLE001
            logger.exception("Nuvio catalog list failed")
            catalogs = []
    try:
        return json.dumps(nuvio_addon.manifest(_nuvio_public_logo(), catalogs=catalogs))
    except Exception:  # noqa: BLE001
        logger.exception("Nuvio manifest failed")
        return json.dumps(nuvio_addon.manifest(None, catalogs=catalogs))


def _nuvio_account(token=None):
    """Resolve the MediaTrail account that should receive Nuvio playback."""
    try:
        if token:
            return users.models.User.objects.get(token=token)
        return _select_nuvio_account_legacy()
    except users.models.User.DoesNotExist:
        logger.warning("Nuvio addon called with unknown token")
        return None
    except Exception:  # noqa: BLE001
        logger.exception("Could not read the MediaTrail account for Nuvio")
        return None


def _select_nuvio_account_legacy():
    """Untokened addon URL: only valid when exactly one account exists."""
    model = users.models.User
    total = model.objects.count()
    if total == 0:
        return None
    if total == 1:
        return model.objects.order_by("id").first()
    logger.warning(
        "Nuvio player/manifest called without account token while %s users exist; "
        "ignored. Install Settings → Integrations → Nuvio for each account.",
        total,
    )
    return None


@login_not_required
@csrf_exempt
@require_http_methods(["GET", "OPTIONS"])
def nuvio_manifest(request, token=None):
    """Serve the addon manifest Nuvio installs."""
    if request.method == "OPTIONS":
        return _nuvio_cors(HttpResponse(status=204))
    user = _nuvio_account(token)
    if token is not None and user is None:
        return _nuvio_cors(HttpResponse(status=401))
    return _nuvio_cors(
        HttpResponse(
            _nuvio_manifest_body(user),
            content_type="application/json",
        ),
    )


@login_not_required
@csrf_exempt
@require_http_methods(["GET", "OPTIONS"])
def nuvio_catalog(request, media_type, catalog_id, extra=None, token=None):
    """Serve one MediaTrail list as a Stremio catalog shelf."""
    if request.method == "OPTIONS":
        return _nuvio_cors(HttpResponse(status=204))
    user = _nuvio_account(token)
    if user is None:
        return _nuvio_cors(HttpResponse(status=401))
    skip = 0
    if extra:
        match = re.search(r"skip[=:](\d+)", extra)
        if match:
            skip = int(match.group(1))
    skip_param = request.GET.get("skip")
    if skip_param and str(skip_param).isdigit():
        skip = int(skip_param)
    from integrations.nuvio_library import catalog_metas

    metas = catalog_metas(user, catalog_id, media_type, skip=skip)
    if metas is None:
        return _nuvio_cors(HttpResponse(status=404))
    return _nuvio_cors(
        HttpResponse(
            json.dumps({"metas": metas}),
            content_type="application/json",
        ),
    )


@login_not_required
@csrf_exempt
@require_http_methods(["GET", "OPTIONS"])
def nuvio_player(request, media_type, video_id, extra=None, token=None):
    """Record a Nuvio player event for the MediaTrail account in the URL."""
    if request.method == "OPTIONS":
        return _nuvio_cors(HttpResponse(status=204))
    user = _nuvio_account(token)
    if user is not None:
        try:
            nuvio_addon.handle_player(
                user,
                media_type,
                video_id,
                extra,
                request.GET,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Nuvio player event failed")
    return _nuvio_cors(JsonResponse({}))


@login_not_required
@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def nuvio_watched(request):
    """Apply mark-watched / mark-unwatched from Nuvio over Bearer auth.

    Token stays in the Authorization header so nginx access logs never see it.
    Playback continues to use the separate player addon routes.
    """
    if request.method == "OPTIONS":
        return _nuvio_cors(
            HttpResponse(status=204),
            methods="POST, OPTIONS",
        )
    token = _nuvio_bearer_token(request)
    if not token:
        return _nuvio_cors(
            JsonResponse({"error": "missing_token"}, status=401),
            methods="POST, OPTIONS",
        )
    user = _nuvio_account(token)
    if user is None:
        return _nuvio_cors(
            JsonResponse({"error": "invalid_token"}, status=401),
            methods="POST, OPTIONS",
        )
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _nuvio_cors(
            JsonResponse({"error": "invalid_json"}, status=400),
            methods="POST, OPTIONS",
        )
    try:
        result = nuvio_watched_api.apply_watched_request(user, payload)
    except nuvio_watched_api.WatchedRequestError as exc:
        return _nuvio_cors(
            JsonResponse({"error": exc.code, "detail": exc.message}, status=exc.status),
            methods="POST, OPTIONS",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Nuvio watched API failed")
        return _nuvio_cors(
            JsonResponse({"error": "internal_error"}, status=500),
            methods="POST, OPTIONS",
        )
    return _nuvio_cors(JsonResponse(result), methods="POST, OPTIONS")


@login_not_required
@csrf_exempt
@require_POST
def jellyfin_webhook(request, token):
    """Handle Jellyfin webhook notifications for media playback."""
    try:
        user = users.models.User.objects.get(token=token)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Jellyfin webhook: Invalid token: %s",
            token,
        )
        return HttpResponse(status=401)

    # Attach User instance so history_user_id is populated
    request.user = user
    data = request.body
    if not data:
        logger.warning("Missing payload in Jellyfin webhook request")
        return HttpResponse("Missing payload", status=400)

    payload = json.loads(data)
    processor = jellyfin.JellyfinWebhookProcessor()
    processor.process_payload(payload, user)
    return HttpResponse(status=200)


@login_not_required
@csrf_exempt
@require_POST
def plex_webhook(request, token):
    """Handle Plex webhook notifications for media playback."""
    try:
        user = users.models.User.objects.get(token=token)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Plex webhook: Invalid token: %s",
            token,
        )
        return HttpResponse(status=401)

    # Attach User instance so history_user_id is populated
    request.user = user

    # https://support.plex.tv/hc/en-us/articles/115002267687-Webhooks
    # As stated above, the payload is sent in JSON format inside a multipart
    # HTTP POST request. For the media.play and media.rate events, a second part of
    # the POST request contains a JPEG thumbnail for the media.

    data = request.POST.get("payload")
    if not data:
        logger.warning("Missing payload in Plex webhook request")
        return HttpResponse("Missing payload", status=400)

    payload = json.loads(data)
    processor = plex.PlexWebhookProcessor()
    processor.process_payload(payload, user)
    return HttpResponse(status=200)


@login_not_required
@csrf_exempt
@require_POST
def emby_webhook(request, token):
    """Handle Emby webhook notifications for media playback."""
    try:
        user = users.models.User.objects.get(token=token)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Emby webhook: Invalid token: %s",
            token,
        )
        return HttpResponse(status=401)

    # Attach User instance so history_user_id is populated
    request.user = user

    # The payload is sent in JSON format inside a multipart
    # HTTP POST request.

    data = request.POST.get("data")
    if not data:
        logger.warning("Missing payload in Emby webhook request")
        return HttpResponse("Missing payload", status=400)

    payload = json.loads(data)
    processor = emby.EmbyWebhookProcessor()
    processor.process_payload(payload, user)
    return HttpResponse(status=200)
