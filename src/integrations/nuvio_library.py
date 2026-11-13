"""Two-way sync: Nuvio native Library ↔ designated MediaTrail CustomList."""

from __future__ import annotations

import logging
import re

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from app.models import Item, MediaTypes, Movie, Sources, Status, TV
from app.providers import services
from integrations.imports.nuvio import NuvioClient, NuvioError, _imdb_id, _split_content_id
from integrations.models import NuvioAccount
from lists.models import CustomList, CustomListItem

logger = logging.getLogger(__name__)

OUTBOUND_TTL_SECONDS = 15 * 60
_IMDB_ID = re.compile(r"(tt\d+)", re.IGNORECASE)
LIBRARY_CONTENT_TYPES = {"movie": MediaTypes.MOVIE.value, "series": MediaTypes.TV.value}


def library_sync_ready(user):
    """True when library sync is on and a watchlist CustomList is selected."""
    if not getattr(user, "nuvio_sync_library_enabled", False):
        return False
    try:
        account = user.nuvio_account
    except NuvioAccount.DoesNotExist:
        return False
    return account.watchlist_list_id is not None


def designated_watchlist(user):
    """Return the CustomList selected for Nuvio Library sync, or None."""
    try:
        account = user.nuvio_account
    except NuvioAccount.DoesNotExist:
        return None
    return account.watchlist_list


def remove_from_nuvio_watchlist(user, item=None, *, tmdb_id=None, media_type=None):
    """Drop a title from the designated watchlist and the Nuvio Library.

    Safe to call repeatedly. Covers movie Completed / 90% stop and series
    In Progress (including mid-watch episode resume).
    """
    if item is None and tmdb_id and media_type:
        item = Item.objects.filter(
            media_id=str(tmdb_id),
            source=Sources.TMDB.value,
            media_type=media_type,
            season_number__isnull=True,
            episode_number__isnull=True,
        ).first()
    if item is None:
        return
    if item.media_type not in {MediaTypes.MOVIE.value, MediaTypes.TV.value}:
        # Season/episode progress maps to the parent show for Nuvio Library.
        if item.media_type == MediaTypes.SEASON.value:
            tv = TV.objects.filter(user=user, item__media_id=item.media_id).first()
            item = tv.item if tv is not None else None
        elif item.media_type == MediaTypes.EPISODE.value:
            item = Item.objects.filter(
                media_id=item.media_id,
                source=item.source,
                media_type=MediaTypes.TV.value,
                season_number__isnull=True,
                episode_number__isnull=True,
            ).first()
        else:
            return
    if item is None or item.media_type not in {
        MediaTypes.MOVIE.value,
        MediaTypes.TV.value,
    }:
        return

    watchlist = designated_watchlist(user)
    if watchlist is not None:
        deleted, _ = CustomListItem.objects.filter(
            custom_list=watchlist,
            item=item,
        ).delete()
        if deleted:
            logger.info("Removed %s from watchlist %s", item, watchlist)

    if not library_sync_ready(user) and watchlist is None:
        # Still try Nuvio delete when sync was on earlier / account exists.
        pass
    if not _has_nuvio_account(user):
        return
    keys = _library_keys_for_item(user, item)
    if not keys:
        return
    for key in keys:
        _mark_pending(user.id, key, operation="delete")
        _clear_pending(user.id, key, operation="upsert")
    from integrations.tasks import delete_nuvio_library_item

    delete_nuvio_library_item.delay(user.id, keys)


def enqueue_library_upsert(user, item):
    """Queue a Nuvio Library push when an item is added to the watchlist."""
    if not library_sync_ready(user):
        return
    if item.media_type not in {MediaTypes.MOVIE.value, MediaTypes.TV.value}:
        return
    if item.source != Sources.TMDB.value:
        return
    payloads = _library_payloads_for_item(user, item)
    if not payloads:
        return
    for payload in payloads:
        _clear_pending(user.id, payload, operation="delete")
        _mark_pending(user.id, payload, operation="upsert")
    from integrations.tasks import push_nuvio_library_item

    push_nuvio_library_item.delay(user.id, payloads)


def enqueue_library_delete(user, item):
    """Queue a Nuvio Library delete when an item leaves the watchlist."""
    if not library_sync_ready(user):
        return
    if item.media_type not in {MediaTypes.MOVIE.value, MediaTypes.TV.value}:
        return
    keys = _library_keys_for_item(user, item)
    if not keys:
        return
    for key in keys:
        _clear_pending(user.id, key, operation="upsert")
        _mark_pending(user.id, key, operation="delete")
    from integrations.tasks import delete_nuvio_library_item

    delete_nuvio_library_item.delay(user.id, keys)


def sync_library_for_user(user, *, bootstrap=False):
    """Pull Nuvio library changes into the designated watchlist (and push gaps)."""
    if not library_sync_ready(user):
        return
    account = user.nuvio_account
    client = NuvioClient(account)
    watchlist = account.watchlist_list
    if bootstrap or not account.library_bootstrapped:
        _bootstrap(user, client, watchlist, account)
        return
    since = account.library_cursor or 0
    highest = since
    for row in client.iter_library_delta(since):
        _apply_library_row(user, watchlist, account, row)
        event_id = int(row.get("event_id") or 0)
        if event_id > highest:
            highest = event_id
    if highest != since:
        account.library_cursor = highest
        account.save(update_fields=["library_cursor"])


def _bootstrap(user, client, watchlist, account):
    """First sync: union both sides; skip MT titles already in progress/done."""
    tip = client.library_cursor()
    remote_rows = list(client.iter_library())
    remote_by_key = {}
    for row in remote_rows:
        parsed = _parse_library_row(row)
        if parsed is None:
            continue
        remote_by_key[_row_key(parsed)] = (row, parsed)

    local_items = list(
        watchlist.items.filter(
            media_type__in=[MediaTypes.MOVIE.value, MediaTypes.TV.value],
            source=Sources.TMDB.value,
        ),
    )
    local_keys = set()
    for item in local_items:
        for key in _library_keys_for_item(user, item):
            local_keys.add(_key_identity(key))

    stale_remote_keys = []
    for row, parsed in remote_by_key.values():
        resolved = _resolve_parsed_to_tmdb(account, parsed)
        if resolved is None:
            continue
        if _should_skip_inbound(user, resolved):
            stale_remote_keys.extend(_keys_from_parsed(parsed))
            continue
        item = _ensure_item(user, account, resolved)
        if item is None:
            continue
        CustomListItem.objects.get_or_create(custom_list=watchlist, item=item)
        local_keys.add(_row_key(parsed))

    for item in local_items:
        if _local_progress_blocks_watchlist(user, item):
            CustomListItem.objects.filter(custom_list=watchlist, item=item).delete()
            enqueue_library_delete(user, item)
            continue
        payloads = _library_payloads_for_item(user, item)
        missing = [
            payload
            for payload in payloads
            if _key_identity(payload) not in {
                _row_key(p) for _, p in remote_by_key.values()
            }
        ]
        if missing:
            for payload in missing:
                _mark_pending(user.id, payload, operation="upsert")
            client.push_library_items(missing)

    if stale_remote_keys:
        for key in stale_remote_keys:
            _mark_pending(user.id, key, operation="delete")
        client.delete_library_items(stale_remote_keys)

    account.library_cursor = tip
    account.library_bootstrapped = True
    account.save(update_fields=["library_cursor", "library_bootstrapped"])


def _apply_library_row(user, watchlist, account, row):
    if _is_echo(user.id, row):
        return
    operation = str(row.get("operation") or "upsert").lower()
    parsed = _parse_library_row(row)
    if parsed is None:
        return
    if operation == "delete":
        resolved = _resolve_parsed_to_tmdb(account, parsed) or parsed
        item = _find_item(resolved)
        if item is not None:
            CustomListItem.objects.filter(custom_list=watchlist, item=item).delete()
        return
    resolved = _resolve_parsed_to_tmdb(account, parsed)
    if resolved is None:
        return
    if _should_skip_inbound(user, resolved):
        # Already watching/done in MediaTrail: keep Nuvio clean too.
        keys = _keys_from_parsed(parsed)
        if keys:
            for key in keys:
                _mark_pending(user.id, key, operation="delete")
            from integrations.tasks import delete_nuvio_library_item

            delete_nuvio_library_item.delay(user.id, keys)
        return
    item = _ensure_item(user, account, resolved)
    if item is None:
        return
    CustomListItem.objects.get_or_create(custom_list=watchlist, item=item)


def _resolve_parsed_to_tmdb(account, parsed):
    """Normalize library row to TMDB media_id for local matching."""
    resolved = dict(parsed)
    if resolved["source"] == "imdb":
        tmdb_id = _map_imdb_to_tmdb(
            account,
            resolved["media_id"],
            resolved["media_type"],
        )
        if not tmdb_id:
            return None
        resolved["media_id"] = str(tmdb_id)
        resolved["source"] = Sources.TMDB.value
    return resolved


def _should_skip_inbound(user, parsed):
    media_type = parsed["media_type"]
    media_id = str(parsed["media_id"])
    if media_type == MediaTypes.MOVIE.value:
        return Movie.objects.filter(
            user=user,
            item__media_id=media_id,
            item__source=Sources.TMDB.value,
            status=Status.COMPLETED.value,
        ).exists()
    if media_type == MediaTypes.TV.value:
        return TV.objects.filter(
            user=user,
            item__media_id=media_id,
            item__source=Sources.TMDB.value,
            status__in=[Status.IN_PROGRESS.value, Status.COMPLETED.value],
        ).exists()
    return False


def _local_progress_blocks_watchlist(user, item):
    if item.media_type == MediaTypes.MOVIE.value:
        return Movie.objects.filter(
            user=user,
            item=item,
            status=Status.COMPLETED.value,
        ).exists()
    if item.media_type == MediaTypes.TV.value:
        return TV.objects.filter(
            user=user,
            item=item,
            status__in=[Status.IN_PROGRESS.value, Status.COMPLETED.value],
        ).exists()
    return False


def _parse_library_row(row):
    if not isinstance(row, dict):
        return None
    content_type = str(row.get("content_type") or "").lower()
    media_type = LIBRARY_CONTENT_TYPES.get(content_type)
    if media_type is None:
        return None
    content_id = str(row.get("content_id") or "").strip()
    title = str(row.get("name") or row.get("title") or content_id or "untitled")
    try:
        source, media_id, _extra = _split_content_id(content_id, title)
    except Exception:
        imdb = _imdb_id(content_id)
        if imdb is None:
            return None
        source, media_id = "imdb", imdb
    return {
        "content_id": content_id,
        "content_type": content_type,
        "media_type": media_type,
        "source": source,
        "media_id": str(media_id),
        "title": title,
        "poster": row.get("poster"),
        "added_at": row.get("added_at") or row.get("addedAt"),
    }


def _ensure_item(user, account, parsed):
    media_id = parsed["media_id"]
    source = parsed["source"]
    media_type = parsed["media_type"]
    if source == "imdb":
        tmdb_id = _map_imdb_to_tmdb(account, media_id, media_type)
        if not tmdb_id:
            return None
        media_id = str(tmdb_id)
        source = Sources.TMDB.value
    item = Item.objects.filter(
        media_id=media_id,
        source=source,
        media_type=media_type,
        season_number__isnull=True,
        episode_number__isnull=True,
    ).first()
    if item is not None:
        return item
    try:
        metadata = services.get_media_metadata(media_type, media_id, source)
    except Exception:
        logger.exception("Library metadata failed for %s %s", media_type, media_id)
        return None
    return Item.objects.create(
        media_id=str(media_id),
        source=source,
        media_type=media_type,
        title=metadata.get("title") or parsed["title"],
        image=metadata.get("image") or parsed.get("poster") or "",
    )


def _find_item(parsed):
    media_id = parsed["media_id"]
    source = parsed["source"]
    media_type = parsed["media_type"]
    if source == "imdb":
        # Prefer TMDB item via map if present on any account map is handled by caller.
        return Item.objects.filter(
            Q(media_id=media_id, source="imdb", media_type=media_type)
            | Q(
                # unmatched; caller should map first for upserts
                media_id=media_id,
                media_type=media_type,
            ),
            season_number__isnull=True,
            episode_number__isnull=True,
        ).first()
    return Item.objects.filter(
        media_id=str(media_id),
        source=source,
        media_type=media_type,
        season_number__isnull=True,
        episode_number__isnull=True,
    ).first()


def _map_imdb_to_tmdb(account, imdb_id, media_type):
    imdb_id = str(imdb_id).lower()
    mapping = dict(account.imdb_map or {})
    if imdb_id in mapping and mapping[imdb_id]:
        return str(mapping[imdb_id])
    try:
        from app.providers import tmdb as tmdb_provider

        payload = tmdb_provider.find(imdb_id, "imdb_id") or {}
    except Exception:
        logger.exception("IMDb→TMDB failed for %s", imdb_id)
        mapping[imdb_id] = ""
        account.imdb_map = mapping
        account.save(update_fields=["imdb_map"])
        return None
    bucket = (
        "movie_results"
        if media_type == MediaTypes.MOVIE.value
        else "tv_results"
    )
    rows = payload.get(bucket) or []
    tmdb_id = str(rows[0]["id"]) if rows else ""
    mapping[imdb_id] = tmdb_id
    account.imdb_map = mapping
    account.save(update_fields=["imdb_map"])
    return tmdb_id or None


def resolve_imdb_id_cached(user, tmdb_id, media_type):
    """TMDB→IMDb using imdb_map first; persist new lookups into the map."""
    tmdb_id = str(tmdb_id)
    try:
        account = user.nuvio_account
    except NuvioAccount.DoesNotExist:
        account = None
    if account is not None:
        for imdb_id, mapped in (account.imdb_map or {}).items():
            if str(mapped) == tmdb_id and _IMDB_ID.fullmatch(str(imdb_id)):
                return str(imdb_id).lower()
    cache_key = f"nuvio_imdb:{media_type}:{tmdb_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached if cached != "-" else None
    try:
        metadata = services.get_media_metadata(media_type, tmdb_id, Sources.TMDB.value)
    except Exception:
        logger.exception("Could not resolve IMDb for TMDB %s", tmdb_id)
        cache.set(cache_key, "-", 3600)
        return None
    links = (metadata or {}).get("external_links") or {}
    match = _IMDB_ID.search(str(links.get("IMDb") or ""))
    if not match:
        cache.set(cache_key, "-", 3600)
        return None
    imdb_id = match.group(1).lower()
    cache.set(cache_key, imdb_id, 7 * 24 * 3600)
    if account is not None:
        mapping = dict(account.imdb_map or {})
        mapping[imdb_id] = tmdb_id
        account.imdb_map = mapping
        account.save(update_fields=["imdb_map"])
    return imdb_id


def catalog_manifest_entries(user):
    """Stremio catalog descriptors for every CustomList the user can view."""
    lists = CustomList.objects.get_user_lists(user)
    catalogs = []
    for custom_list in lists:
        movie_count = custom_list.items.filter(media_type=MediaTypes.MOVIE.value).count()
        series_count = custom_list.items.filter(media_type=MediaTypes.TV.value).count()
        # Always advertise both types so new items appear without reinstalling.
        # Empty shelves return metas: [] — Nuvio may still show an empty row.
        catalogs.append(
            {
                "type": "movie",
                "id": f"mt-list-{custom_list.id}-movie",
                "name": _catalog_name(custom_list.name, "movie", movie_count, series_count),
                "extra": [{"name": "skip", "isRequired": False}],
            },
        )
        catalogs.append(
            {
                "type": "series",
                "id": f"mt-list-{custom_list.id}-series",
                "name": _catalog_name(custom_list.name, "series", movie_count, series_count),
                "extra": [{"name": "skip", "isRequired": False}],
            },
        )
    return catalogs


def _catalog_name(list_name, catalog_type, movie_count, series_count):
    base = (list_name or "List").strip() or "List"
    if movie_count and series_count:
        suffix = "Movies" if catalog_type == "movie" else "Series"
        return f"{base} — {suffix}"
    return base


def catalog_metas(user, catalog_id, catalog_type, *, skip=0, limit=100):
    """Build Stremio metas for one list catalog (IMDb ids via cache)."""
    match = re.fullmatch(r"mt-list-(\d+)-(movie|series)", catalog_id or "")
    if match is None:
        return None
    list_id = int(match.group(1))
    expected_type = match.group(2)
    if expected_type != catalog_type:
        return []
    media_type = (
        MediaTypes.MOVIE.value if catalog_type == "movie" else MediaTypes.TV.value
    )
    custom_list = (
        CustomList.objects.filter(Q(owner=user) | Q(collaborators=user), id=list_id)
        .distinct()
        .first()
    )
    if custom_list is None:
        return None
    items = list(
        custom_list.items.filter(
            media_type=media_type,
            source=Sources.TMDB.value,
        ).order_by("-customlistitem__date_added")[skip : skip + limit],
    )
    metas = []
    for item in items:
        imdb_id = resolve_imdb_id_cached(user, item.media_id, media_type)
        meta_id = imdb_id or f"tmdb:{item.media_id}"
        metas.append(
            {
                "id": meta_id,
                "type": catalog_type,
                "name": item.title,
                "poster": item.image or None,
            },
        )
    return metas


def _library_payloads_for_item(user, item):
    content_type = "movie" if item.media_type == MediaTypes.MOVIE.value else "series"
    added_at = int(timezone.now().timestamp() * 1000)
    payloads = []
    for content_id in _content_id_variants(user, item.media_id, item.media_type):
        payloads.append(
            {
                "content_id": content_id,
                "content_type": content_type,
                "name": item.title or content_id,
                "poster": item.image or None,
                "added_at": added_at,
            },
        )
    return payloads


def _library_keys_for_item(user, item):
    content_type = "movie" if item.media_type == MediaTypes.MOVIE.value else "series"
    return [
        {"content_id": content_id, "content_type": content_type}
        for content_id in _content_id_variants(user, item.media_id, item.media_type)
    ]


def _keys_from_parsed(parsed):
    return [
        {
            "content_id": parsed["content_id"],
            "content_type": parsed["content_type"],
        },
    ]


def _content_id_variants(user, tmdb_id, media_type):
    tmdb_id = str(tmdb_id).strip()
    variants = [f"tmdb:{tmdb_id}"]
    imdb_id = resolve_imdb_id_cached(user, tmdb_id, media_type)
    if imdb_id:
        variants.append(imdb_id)
        variants.append(f"imdb:{imdb_id}")
    seen = set()
    ordered = []
    for value in variants:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _row_key(parsed):
    return f"{parsed['content_type']}:{parsed['content_id']}".lower()


def _key_identity(payload):
    content_id = str(payload.get("content_id") or "").strip().lower()
    content_type = str(payload.get("content_type") or "").strip().lower()
    return f"{content_type}:{content_id}"


def _has_nuvio_account(user):
    return NuvioAccount.objects.filter(user=user).exists()


def _is_echo(user_id, row):
    operation = str(row.get("operation") or "upsert").lower()
    if operation not in {"upsert", "delete"}:
        operation = "upsert"
    identity = _key_identity(row)
    key = _cache_key(user_id, identity, operation=operation)
    return bool(key and cache.get(key))


def _mark_pending(user_id, payload, *, operation):
    identity = _key_identity(payload)
    key = _cache_key(user_id, identity, operation=operation)
    if key:
        cache.set(key, True, OUTBOUND_TTL_SECONDS)


def _clear_pending(user_id, payload, *, operation):
    identity = _key_identity(payload)
    key = _cache_key(user_id, identity, operation=operation)
    if key:
        cache.delete(key)


def _cache_key(user_id, identity, *, operation):
    if not identity:
        return None
    op = "delete" if operation == "delete" else "upsert"
    return f"nuvio_library_outbound:{user_id}:{op}:{identity}"
