"""Apply Nuvio mark-watched / mark-unwatched pushes over Bearer auth.

Companion apps POST here so the MediaTrail access token never appears in the
URL (and therefore not in nginx access logs). Playback remains on the separate
player addon routes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone

from django.utils.dateparse import parse_datetime

from integrations import nuvio_outbound
from integrations.imports import helpers as import_helpers
from integrations.imports.nuvio import NuvioImporter
from integrations.models import NuvioAccount

logger = logging.getLogger(__name__)

ACTIONS = frozenset({"watched", "unwatched"})
TYPES = frozenset({"movie", "series"})


class WatchedRequestError(Exception):
    """Invalid payload or policy rejection for the watched endpoint."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def apply_watched_request(user, payload):
    """Apply one watched/unwatched mutation for ``user``.

    Returns a dict with ``status`` of ``ok`` or ``skipped``.
    """
    if not isinstance(payload, dict):
        raise WatchedRequestError("invalid_json", "Request body must be a JSON object.")

    action = str(payload.get("action") or "").strip().lower()
    content_type = str(payload.get("type") or payload.get("content_type") or "").strip().lower()
    content_id = str(payload.get("id") or payload.get("content_id") or "").strip()
    if action not in ACTIONS:
        raise WatchedRequestError(
            "invalid_action",
            "action must be 'watched' or 'unwatched'.",
        )
    if content_type not in TYPES:
        raise WatchedRequestError(
            "invalid_type",
            "type must be 'movie' or 'series'.",
        )
    if not content_id:
        raise WatchedRequestError("missing_id", "id (IMDb / content id) is required.")

    season = payload.get("season")
    episode = payload.get("episode")
    if content_type == "series":
        if season is None or episode is None:
            raise WatchedRequestError(
                "missing_episode",
                "season and episode are required for series.",
            )
        try:
            season = int(season)
            episode = int(episode)
        except (TypeError, ValueError) as exc:
            raise WatchedRequestError(
                "invalid_episode",
                "season and episode must be integers.",
            ) from exc

    if action == "watched" and not getattr(user, "nuvio_sync_mark_played_enabled", False):
        return {"status": "skipped", "reason": "mark_played_disabled"}
    if action == "unwatched" and not getattr(
        user,
        "nuvio_sync_mark_unplayed_enabled",
        False,
    ):
        return {"status": "skipped", "reason": "mark_unplayed_disabled"}

    if not NuvioAccount.objects.filter(user=user).exists():
        raise WatchedRequestError(
            "nuvio_not_configured",
            "Import Nuvio once before using watched sync.",
            status=400,
        )

    operation = "upsert" if action == "watched" else "delete"
    row = {
        "content_id": content_id,
        "content_type": content_type,
        "title": str(payload.get("title") or content_id),
        "operation": operation,
        "watched_at": _watched_at_ms(payload.get("watched_at"), required=operation == "upsert"),
    }
    if content_type == "series":
        row["season"] = season
        row["episode"] = episode

    try:
        # No Cloud HTTP: apply uses local DB only. Avoid decrypting credentials.
        importer = NuvioImporter(
            user,
            client=_UnusedNuvioClient(),
            mode="overwrite",
            gate_upserts=True,
        )
    except import_helpers.MediaImportError as exc:
        raise WatchedRequestError("nuvio_not_configured", str(exc), status=400) from exc

    ok = importer._apply(row, operation=operation, event_id=None)
    if not ok:
        raise WatchedRequestError(
            "apply_failed",
            "Could not apply the watched change (provider may be unavailable).",
            status=502,
        )
    # Persist watched_keys updates from _apply when not deferred.
    importer._flush_progress()
    # Cloud delta will repeat this change shortly; treat it as an echo.
    nuvio_outbound.note_direct_watched_apply(user, row, operation=operation)
    logger.info(
        "Nuvio watched API action=%s type=%s id=%s season=%s episode=%s user=%s",
        action,
        content_type,
        content_id,
        season,
        episode,
        user.id,
    )
    return {
        "status": "ok",
        "action": action,
        "type": content_type,
        "id": content_id,
        "season": season,
        "episode": episode,
    }


class _UnusedNuvioClient:
    """Placeholder so NuvioImporter skips NuvioClient credential decrypt."""


def _watched_at_ms(value, *, required):
    """Normalize watched_at to epoch milliseconds for the Nuvio importer."""
    if value is None or value == "":
        if required:
            return int(datetime.now(tz=dt_timezone.utc).timestamp() * 1000)
        return None
    if isinstance(value, bool):
        raise WatchedRequestError("invalid_watched_at", "watched_at must be a time value.")
    if isinstance(value, (int, float)):
        number = int(value)
        # Seconds vs milliseconds heuristic (same idea as the importer).
        if number < 10_000_000_000:
            number *= 1000
        return number
    text = str(value).strip()
    if text.isdigit():
        return _watched_at_ms(int(text), required=required)
    parsed = parse_datetime(text)
    if parsed is None:
        raise WatchedRequestError(
            "invalid_watched_at",
            "watched_at must be ISO-8601 or epoch milliseconds.",
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return int(parsed.timestamp() * 1000)
