"""Hybrid recommendation pipeline: TMDB + IMDb + Gemini → unified TMDB cards."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db import close_old_connections

from app.models import MediaTypes, Sources
from app.providers import gemini_recommendations, imdb_recommendations, services, tmdb
from app.recommendation_sources import (
    SOURCE_AI,
    SOURCE_IMDB,
    SOURCE_TMDB,
    parse_source_keys,
)

logger = logging.getLogger(__name__)

_LABEL = {
    SOURCE_TMDB: "TMDB",
    SOURCE_IMDB: "IMDb",
    SOURCE_AI: "AI",
}

# AI and IMDb first so cultural / more-like-this hits are not buried under TMDB.
_MERGE_PRIORITY = (SOURCE_AI, SOURCE_IMDB, SOURCE_TMDB)

# Keep cold-path latency bounded; cache makes later loads cheap.
_MAX_IMDB_RESOLVE = 10
_MAX_AI_RESOLVE = 8
_RESOLVE_WORKERS = 4


def build_recommendations(user, media_metadata: dict, media_type: str, sources=None):
    """Return deduped recommendation item dicts with a ``sources`` list."""
    if media_type not in (MediaTypes.MOVIE.value, MediaTypes.TV.value):
        return list((media_metadata.get("related") or {}).get("recommendations") or [])

    selected = (
        list(sources)
        if sources is not None
        else parse_source_keys(None, user)
    )
    if not selected:
        selected = [SOURCE_TMDB]

    seed_id = str(media_metadata.get("media_id") or "")
    buckets: dict[str, list[dict]] = {}

    def _run(key: str) -> tuple[str, list[dict]]:
        close_old_connections()
        try:
            if key == SOURCE_TMDB:
                return key, _from_tmdb(media_metadata)
            if key == SOURCE_IMDB:
                return key, _from_imdb(media_metadata, media_type)
            if key == SOURCE_AI:
                return key, _from_ai(user, media_metadata, media_type)
            return key, []
        except Exception:
            logger.exception("Recommendation source %s failed", key)
            return key, []
        finally:
            close_old_connections()

    if len(selected) == 1:
        key, items = _run(selected[0])
        buckets[key] = items
    else:
        # Parallelize slow sources (IMDb resolve + Gemini). TMDB is already local.
        with ThreadPoolExecutor(max_workers=min(3, len(selected))) as pool:
            futures = [pool.submit(_run, key) for key in selected]
            for future in as_completed(futures):
                key, items = future.result()
                buckets[key] = items

    for key in selected:
        logger.info(
            "Recommendation source %s returned %s items for %s/%s",
            key,
            len(buckets.get(key) or []),
            media_type,
            seed_id,
        )

    return _merge(buckets, exclude_media_id=seed_id, exclude_type=media_type)


def apply_to_metadata(user, media_metadata: dict, media_type: str, sources=None):
    """Replace ``related.recommendations`` with the hybrid list (in place)."""
    related = media_metadata.setdefault("related", {})
    related["recommendations"] = build_recommendations(
        user,
        media_metadata,
        media_type,
        sources=sources,
    )
    return media_metadata


def fast_initial_sources(preferred: list[str]) -> list[str]:
    """Sources used for the first paint (TMDB when enabled)."""
    if SOURCE_TMDB in preferred:
        return [SOURCE_TMDB]
    return list(preferred[:1]) if preferred else [SOURCE_TMDB]


def needs_deferred_load(preferred: list[str], loaded: list[str]) -> bool:
    """True when preferred sources include slow engines not yet loaded."""
    return any(source in preferred and source not in loaded for source in (SOURCE_AI, SOURCE_IMDB))


def _from_tmdb(media_metadata: dict) -> list[dict]:
    return list((media_metadata.get("related") or {}).get("recommendations") or [])


def _from_imdb(media_metadata: dict, media_type: str) -> list[dict]:
    external = media_metadata.get("external_ids") or {}
    imdb_id = external.get("imdb_id") or ""
    if not imdb_id:
        links = media_metadata.get("external_links") or {}
        imdb_url = links.get("IMDb") or links.get("imdb") or ""
        if "/title/" in imdb_url:
            imdb_id = imdb_url.rstrip("/").split("/")[-1]

    tt_ids = imdb_recommendations.more_like_this_ids(imdb_id, media_type)[
        :_MAX_IMDB_RESOLVE
    ]
    return _resolve_many(
        [(_resolve_imdb, {"imdb_id": tt, "preferred_type": media_type}) for tt in tt_ids]
    )


def _from_ai(user, media_metadata: dict, media_type: str) -> list[dict]:
    year = _seed_year(media_metadata, media_type)
    suggestions = gemini_recommendations.recommend_titles(
        user,
        title=media_metadata.get("title") or "",
        year=year,
        media_type=media_type,
        media_id=media_metadata.get("media_id"),
    )[:_MAX_AI_RESOLVE]
    return _resolve_many(
        [
            (
                _resolve_title_year,
                {
                    "title": suggestion.get("title") or "",
                    "year": suggestion.get("year"),
                    "media_type": suggestion.get("media_type") or media_type,
                },
            )
            for suggestion in suggestions
        ]
    )


def _resolve_many(jobs: list[tuple]) -> list[dict]:
    """Run TMDB resolve calls in a small pool; preserve first-seen order."""
    if not jobs:
        return []
    if len(jobs) == 1:
        fn, kwargs = jobs[0]
        item = fn(**kwargs)
        return [item] if item else []

    results = {}

    def _job(index, fn, kwargs):
        close_old_connections()
        try:
            return index, fn(**kwargs)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=min(_RESOLVE_WORKERS, len(jobs))) as pool:
        futures = [
            pool.submit(_job, index, fn, kwargs) for index, (fn, kwargs) in enumerate(jobs)
        ]
        for future in as_completed(futures):
            index, item = future.result()
            results[index] = item

    items = []
    for index in range(len(jobs)):
        item = results.get(index)
        if item:
            items.append(item)
    return items


def _resolve_imdb(imdb_id: str, *, preferred_type: str) -> dict | None:
    try:
        response = tmdb.find(imdb_id, "imdb_id")
    except Exception:
        logger.exception("TMDB find failed for %s", imdb_id)
        return None

    movie_results = response.get("movie_results") or []
    tv_results = response.get("tv_results") or []
    if preferred_type == MediaTypes.TV.value:
        candidates = [(MediaTypes.TV.value, r) for r in tv_results] + [
            (MediaTypes.MOVIE.value, r) for r in movie_results
        ]
    else:
        candidates = [(MediaTypes.MOVIE.value, r) for r in movie_results] + [
            (MediaTypes.TV.value, r) for r in tv_results
        ]

    if not candidates:
        return None
    hit_type, hit = candidates[0]
    return _card_from_tmdb_result(hit, hit_type)


def _resolve_title_year(title: str, year, media_type: str) -> dict | None:
    if not title:
        return None
    if media_type not in (MediaTypes.MOVIE.value, MediaTypes.TV.value):
        media_type = MediaTypes.MOVIE.value

    params = {
        **tmdb.base_params,
        "query": title,
        "page": 1,
    }
    if settings.TMDB_NSFW:
        params["include_adult"] = "true"
    if year:
        if media_type == MediaTypes.MOVIE.value:
            params["year"] = int(year)
        else:
            params["first_air_date_year"] = int(year)

    url = f"{tmdb.base_url}/search/{media_type}"
    try:
        response = services.api_request(Sources.TMDB.value, "GET", url, params=params)
    except Exception:
        logger.exception("TMDB search failed for %r (%s)", title, year)
        return None

    results = response.get("results") or []
    if not results and year:
        params.pop("year", None)
        params.pop("first_air_date_year", None)
        try:
            response = services.api_request(
                Sources.TMDB.value,
                "GET",
                url,
                params=params,
            )
        except Exception:
            return None
        results = response.get("results") or []
    if not results:
        return None
    return _card_from_tmdb_result(results[0], media_type)


def _card_from_tmdb_result(media: dict, media_type: str) -> dict:
    return {
        "source": Sources.TMDB.value,
        "media_type": media_type,
        "media_id": media["id"],
        "title": tmdb.get_title(media),
        "image": tmdb.get_image_url(media.get("poster_path")),
        "sources": [],
    }


def _seed_year(media_metadata: dict, media_type: str):  # noqa: ARG001
    raw = media_metadata.get("start_date") or media_metadata.get("release_date") or ""
    if isinstance(raw, str) and len(raw) >= 4 and raw[:4].isdigit():
        return int(raw[:4])
    details = media_metadata.get("details") or {}
    for key in ("release_date", "first_air_date", "Release Date", "First Air Date"):
        value = details.get(key) or ""
        if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
            return int(value[:4])
    return None


def _merge(buckets: dict[str, list[dict]], *, exclude_media_id: str, exclude_type: str):
    merged = {}
    order = []
    source_keys = [key for key in _MERGE_PRIORITY if key in buckets]
    source_keys.extend(key for key in buckets if key not in source_keys)
    for source_key in source_keys:
        items = buckets.get(source_key) or []
        label = _LABEL.get(source_key, source_key)
        for item in items:
            media_id = str(item.get("media_id") or "")
            mtype = item.get("media_type") or exclude_type
            if not media_id:
                continue
            if media_id == str(exclude_media_id) and mtype == exclude_type:
                continue
            key = (mtype, media_id)
            if key not in merged:
                card = {
                    "source": item.get("source") or Sources.TMDB.value,
                    "media_type": mtype,
                    "media_id": item["media_id"],
                    "title": item.get("title") or "",
                    "image": item.get("image"),
                    "sources": [label],
                }
                merged[key] = card
                order.append(key)
            elif label not in merged[key]["sources"]:
                merged[key]["sources"].append(label)
    return [merged[key] for key in order]
