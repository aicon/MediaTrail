"""Contains views for importing and exporting media data from various sources."""

import json
import logging
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
    """Start Trakt browser OAuth (auth.trakt.tv + PKCE S256)."""
    if not trakt.device_client_id():
        messages.error(request, "The new Trakt API is not configured on this server.")
        return redirect("import_data")

    redirect_uri = app_helpers.build_absolute_app_url(
        request,
        reverse("import_trakt_private"),
    )
    code_verifier, code_challenge = trakt.make_pkce_pair()
    state = {
        "mode": request.POST["mode"],
        "frequency": request.POST["frequency"],
        "time": request.POST["time"],
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    state_token = secrets.token_urlsafe(32)
    request.session[state_token] = state
    return redirect(
        f"{trakt.TRAKT_AUTHORIZE_URL}?{
            urlencode(
                {
                    'client_id': trakt.device_client_id(),
                    'redirect_uri': redirect_uri,
                    'response_type': 'code',
                    'state': state_token,
                    'code_challenge': code_challenge,
                    'code_challenge_method': 'S256',
                }
            )
        }",
    )


@require_GET
def import_trakt_private(request):
    """Handle Trakt PKCE callback and schedule a private import."""
    state_token = request.GET.get("state")
    state = request.session.pop(state_token, None) if state_token else None
    if not state:
        messages.error(request, "Invalid or expired Trakt authorization request.")
        return redirect("import_data")

    # One-shot verifier: never reuse even if the token exchange fails.
    code_verifier = state.pop("code_verifier", None)

    if not request.GET.get("code"):
        messages.error(request, "Trakt authorization failed.")
        return redirect("import_data")

    redirect_uri = state.get("redirect_uri") or app_helpers.build_absolute_app_url(
        request,
        reverse("import_trakt_private"),
    )
    try:
        oauth_callback = trakt.handle_oauth_callback(
            request,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
    except helpers.MediaImportError as error:
        messages.error(request, str(error))
        return redirect("import_data")

    _queue_trakt_import(
        request,
        username=oauth_callback["username"],
        refresh_token=oauth_callback["refresh_token"],
        state=state,
        auth="pkce",
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
    """View for initiating the SIMKL OAuth2 authorization flow."""
    redirect_uri = app_helpers.build_absolute_app_url(
        request,
        reverse("import_simkl_private"),
    )
    url = "https://simkl.com/oauth/authorize"

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
    """View for getting the SIMKL OAuth2 token."""
    oauth_callback = simkl.get_token(request)
    enc_token = helpers.encrypt(oauth_callback["access_token"])
    state_token = request.GET["state"]

    frequency = request.session[state_token]["frequency"]
    mode = request.session[state_token]["mode"]
    import_time = request.session[state_token]["time"]

    if frequency == "once":
        tasks.import_simkl.delay(token=enc_token, user_id=request.user.id, mode=mode)
        messages.info(request, "The task to import media from Simkl has been queued.")
    else:
        helpers.create_import_schedule(
            oauth_callback["username"],
            request,
            mode,
            frequency,
            import_time,
            "SIMKL",
            token=enc_token,
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


def _nuvio_cors(response):
    """Allow the Nuvio app to call the addon routes."""
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


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


def _nuvio_manifest_body():
    """JSON manifest. A logo problem must not turn the addon into an error page."""
    try:
        return json.dumps(nuvio_addon.manifest(_nuvio_public_logo()))
    except Exception:  # noqa: BLE001
        logger.exception("Nuvio manifest failed")
        return json.dumps(nuvio_addon.manifest(None))


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
    if token is not None and _nuvio_account(token) is None:
        return _nuvio_cors(HttpResponse(status=401))
    return _nuvio_cors(
        HttpResponse(_nuvio_manifest_body(), content_type="application/json"),
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
