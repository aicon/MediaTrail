import logging

from celery import shared_task
from django.contrib.auth import get_user_model

import events
from app.mixins import disable_fetch_releases
from app.models import MediaTypes
from app.templatetags import app_tags
from integrations.imports import (
    anilist,
    goodreads,
    helpers,
    hltb,
    imdb,
    kitsu,
    mal,
    nuvio,
    simkl,
    steam,
    trakt,
    yamtrack,
)

logger = logging.getLogger(__name__)
ERROR_TITLE = "\n\n\n Couldn't import the following media: \n\n"


def format_media_type_display(count, media_type):
    """Format media type display with proper pluralization."""
    if count == 0:
        return None
    if count == 1:
        return f"{count} {dict(MediaTypes.choices).get(media_type, media_type)}"
    return f"{count} {app_tags.media_type_readable_plural(media_type)}"


def format_import_message(imported_counts, warning_messages=None, removed_counts=None):
    """Format the import result message based on counts and warnings."""
    imported_parts = [
        format_media_type_display(count, media_type)
        for media_type, count in (imported_counts or {}).items()
    ]
    imported_parts = [part for part in imported_parts if part is not None]
    removed_parts = [
        format_media_type_display(count, media_type)
        for media_type, count in (removed_counts or {}).items()
    ]
    removed_parts = [part for part in removed_parts if part is not None]

    if imported_parts and removed_parts:
        info_message = (
            f"Imported {helpers.join_with_commas_and(imported_parts)}. "
            f"Removed {helpers.join_with_commas_and(removed_parts)}."
        )
    elif imported_parts:
        info_message = f"Imported {helpers.join_with_commas_and(imported_parts)}."
    elif removed_parts:
        info_message = f"Removed {helpers.join_with_commas_and(removed_parts)}."
    else:
        info_message = "No media was imported."

    if warning_messages:
        return f"{info_message} {ERROR_TITLE} {warning_messages}"
    return info_message


def import_media(
    importer_func,
    identifier,
    user_id,
    mode,
    oauth_username=None,
    **kwargs,
):
    """Handle the import process for different media services."""
    user = get_user_model().objects.get(id=user_id)

    with disable_fetch_releases():
        if oauth_username is None:
            result = importer_func(
                identifier,
                user,
                mode,
                **kwargs,
            )
        else:
            result = importer_func(
                identifier,
                user,
                mode,
                username=oauth_username,
                **kwargs,
            )

    removed_counts = None
    if isinstance(result, tuple) and len(result) == 3:
        imported_counts, warnings, removed_counts = result
    else:
        imported_counts, warnings = result

    events.tasks.reload_calendar.delay()

    return format_import_message(imported_counts, warnings, removed_counts)


@shared_task(name="Sync Nuvio playback")
def sync_nuvio_playback():
    """Refresh Now Watching from each saved Nuvio account."""
    from integrations.models import NuvioAccount

    for account in NuvioAccount.objects.select_related("user"):
        try:
            nuvio.sync_now_watching(account.user)
        except Exception:
            logger.exception("Nuvio playback sync failed for %s", account.user_id)


def _nuvio_sync_accounts():
    """Bootstrapped accounts that opted into interactive watch-history sync."""
    from django.db.models import Q

    from integrations.models import NuvioAccount

    return NuvioAccount.objects.select_related("user").filter(
        bootstrapped=True,
        cursor__isnull=False,
    ).filter(
        Q(user__nuvio_sync_mark_played_enabled=True)
        | Q(user__nuvio_sync_mark_unplayed_enabled=True),
    )


def _nuvio_sync_lock(user_id, *, timeout):
    """Prevent overlapping polls/reconciles for the same MediaTrail user."""
    from django.core.cache import cache

    return cache.add(f"nuvio-watch-sync:{user_id}", "1", timeout=timeout)


def _nuvio_sync_unlock(user_id):
    from django.core.cache import cache

    cache.delete(f"nuvio-watch-sync:{user_id}")


@shared_task(name="Sync Nuvio watch history")
def sync_nuvio_watch_history():
    """Apply only the Nuvio watched-history delta (fast interactive poll)."""
    for account in _nuvio_sync_accounts():
        user_id = account.user_id
        if not _nuvio_sync_lock(user_id, timeout=120):
            logger.info(
                "Nuvio watch-history delta poll skipped; already running user=%s",
                user_id,
            )
            continue
        try:
            logger.info(
                "Nuvio watch-history delta poll start user=%s cursor=%s",
                user_id,
                account.cursor,
            )
            with disable_fetch_releases():
                user = account.user
                user.refresh_from_db(
                    fields=[
                        "nuvio_sync_mark_played_enabled",
                        "nuvio_sync_mark_unplayed_enabled",
                    ],
                )
                nuvio.NuvioImporter(
                    user,
                    mode="new",
                    gate_upserts=True,
                ).sync_delta()
            account.refresh_from_db(fields=["cursor"])
            logger.info(
                "Nuvio watch-history delta poll done user=%s cursor=%s",
                user_id,
                account.cursor,
            )
        except Exception:
            logger.exception(
                "Nuvio watch-history delta sync failed for %s",
                user_id,
            )
        finally:
            _nuvio_sync_unlock(user_id)


@shared_task(name="Sync Nuvio watch history for user")
def sync_nuvio_watch_history_for_user(user_id):
    """Queueable one-shot delta sync after toggles are saved."""
    user = get_user_model().objects.filter(id=user_id).first()
    if user is None:
        return
    if not (
        user.nuvio_sync_mark_played_enabled
        or user.nuvio_sync_mark_unplayed_enabled
    ):
        return
    from integrations.models import NuvioAccount

    try:
        account = user.nuvio_account
    except NuvioAccount.DoesNotExist:
        return
    if not account.bootstrapped or account.cursor is None:
        return
    if not _nuvio_sync_lock(user_id, timeout=120):
        logger.info(
            "Nuvio watch-history one-shot skipped; already running user=%s",
            user_id,
        )
        return
    try:
        logger.info(
            "Nuvio watch-history one-shot start user=%s cursor=%s",
            user_id,
            account.cursor,
        )
        with disable_fetch_releases():
            nuvio.NuvioImporter(
                user,
                mode="new",
                gate_upserts=True,
            ).sync_delta()
    except Exception:
        logger.exception("Nuvio watch-history delta sync failed for %s", user_id)
    finally:
        _nuvio_sync_unlock(user_id)


@shared_task(name="Reconcile Nuvio watch history")
def reconcile_nuvio_watch_history():
    """Full history snapshot + delta so missed unwatches are reconciled."""
    for account in _nuvio_sync_accounts():
        user_id = account.user_id
        if not _nuvio_sync_lock(user_id, timeout=600):
            logger.info(
                "Nuvio watch-history reconcile skipped; already running user=%s",
                user_id,
            )
            continue
        try:
            logger.info(
                "Nuvio watch-history reconcile start user=%s cursor=%s",
                user_id,
                account.cursor,
            )
            with disable_fetch_releases():
                nuvio.NuvioImporter(
                    account.user,
                    mode="new",
                    gate_upserts=True,
                ).import_data()
        except Exception:
            logger.exception(
                "Nuvio watch-history reconcile failed for %s",
                user_id,
            )
        finally:
            _nuvio_sync_unlock(user_id)


@shared_task(name="Import from Nuvio")
def import_nuvio(user_id, mode, username=None):
    """Celery task for importing missing movies and episodes from Nuvio."""
    return import_media(nuvio.importer, username or "", user_id, mode)


@shared_task(
    name="Push Nuvio watched item",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def push_nuvio_watched_item(user_id, items):
    """Upsert watched item variants to Nuvio. Idempotent on retry."""
    user = get_user_model().objects.get(id=user_id)
    if not user.nuvio_sync_mark_played_enabled:
        return
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return
    payload = [
        item
        for item in items
        if isinstance(item, dict) and item.get("content_id")
    ]
    if not payload:
        return
    nuvio.NuvioClient(user.nuvio_account).push_watched_items(payload)


@shared_task(
    name="Delete Nuvio watched item",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def delete_nuvio_watched_item(user_id, keys, progress_keys=None):
    """Delete watched + progress key variants from Nuvio. Idempotent on retry."""
    user = get_user_model().objects.get(id=user_id)
    if not user.nuvio_sync_mark_unplayed_enabled:
        return
    if isinstance(keys, dict):
        keys = [keys]
    if not isinstance(keys, list):
        return
    payload = [
        key for key in keys if isinstance(key, dict) and key.get("content_id")
    ]
    client = nuvio.NuvioClient(user.nuvio_account)
    if payload:
        client.delete_watched_items(payload)
    if isinstance(progress_keys, str):
        progress_keys = [progress_keys]
    if isinstance(progress_keys, list) and progress_keys:
        client.delete_watch_progress(
            [key for key in progress_keys if isinstance(key, str) and key],
        )
@shared_task(name="Import from Trakt")
def import_trakt(
    user_id,
    mode,
    token=None,
    username=None,
    redirect_uri=None,
    auth="legacy",
):
    """Celery task for importing media data from Trakt.

    Can import using either OAuth (token provided) or public username.
    auth "device" refreshes the token with the new Trakt API.
    """
    return import_media(
        trakt.importer,
        token,
        user_id,
        mode,
        username,
        redirect_uri=redirect_uri,
        auth=auth,
    )


@shared_task(name="Import from SIMKL")
def import_simkl(token, user_id, mode, username=None):  # noqa: ARG001
    """Celery task for importing media data from SIMKL."""
    return import_media(simkl.importer, token, user_id, mode)


@shared_task(name="Import from MyAnimeList")
def import_mal(username, user_id, mode):
    """Celery task for importing anime and manga data from MyAnimeList."""
    return import_media(mal.importer, username, user_id, mode)


@shared_task(name="Import from AniList")
def import_anilist(user_id, mode, token=None, username=None):
    """Celery task for importing media data from AniList."""
    return import_media(anilist.importer, token, user_id, mode, username)


@shared_task(name="Import from Kitsu")
def import_kitsu(username, user_id, mode):
    """Celery task for importing anime and manga data from Kitsu."""
    return import_media(kitsu.importer, username, user_id, mode)


@shared_task(name="Import from MediaTrail")
def import_yamtrack(file, user_id, mode):
    """Celery task for importing a MediaTrail CSV backup."""
    return import_media(yamtrack.importer, file, user_id, mode)


@shared_task(name="Import from HowLongToBeat")
def import_hltb(file, user_id, mode):
    """Celery task for importing media data from HowLongToBeat."""
    return import_media(hltb.importer, file, user_id, mode)


@shared_task(name="Import from Steam")
def import_steam(username, user_id, mode):
    """Celery task for importing game data from Steam."""
    return import_media(steam.importer, username, user_id, mode)


@shared_task(name="Import from IMDB")
def import_imdb(file, user_id, mode):
    """Celery task for importing media data from IMDB."""
    return import_media(imdb.importer, file, user_id, mode)


@shared_task(name="Import from GoodReads")
def import_goodreads(file, user_id, mode):
    """Celery task for importing media data from GoodReads."""
    return import_media(goodreads.importer, file, user_id, mode)
