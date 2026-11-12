"""Import Nuvio movies and episodes into MediaTrail.

Writes the local models directly. New mode adds only missing movies and
episodes. Overwrite mode also replaces the watch date of items that are
already tracked. Delete events from Nuvio remove matching local history only
when the user enables mark-unwatched sync.
"""

import logging
import re
from datetime import datetime, timezone

import requests
from cryptography.fernet import InvalidToken
from django.conf import settings
from simple_history.utils import bulk_update_with_history

import app
from app.models import LivePlaybackStatus, MediaTypes, Sources, Status
from app.playback_operations import upsert_live_playback
from app.providers import services
from integrations.imports import helpers
from integrations.imports.helpers import MediaImportError
from integrations.models import NuvioAccount

logger = logging.getLogger(__name__)

NUVIO_BASE_URL = "https://api.nuvio.tv"
# Public client key from the Nuvio API docs. It is not a user secret.
NUVIO_PUBLISHABLE_KEY = "sb_publishable_1Clq8rlTVACkdcZuqr6_AD__xUUC_EN"
PAGE_SIZE = 500
_IMDB_ID = re.compile(r"^tt\d+$", re.IGNORECASE)
_BLOCKING_STATUS = {0, 401, 403, 429, 500, 502, 503, 504}


class NuvioError(Exception):
    """Nuvio rejected the request or returned a payload that cannot continue."""

    def __init__(self, message, status=0):
        """Store the HTTP status. Zero means the connection failed."""
        super().__init__(message)
        self.status = status


class RecordError(ValueError):
    """A history row is not a movie or episode this import can store."""


LIVE_WATCHING_SECONDS = 120
LIVE_VISIBLE_SECONDS = 15 * 60
_MS_THRESHOLD = 10_000
_EPOCH_MS_THRESHOLD = 10_000_000_000


def sync_now_watching(user):
    """Put the newest open Nuvio watch on the home strip."""
    try:
        account = user.nuvio_account
    except NuvioAccount.DoesNotExist:
        return False
    current = _current_nuvio_watch(NuvioClient(account))
    if current is None:
        return False
    _show_nuvio_watch(user, current)
    return True


def _current_nuvio_watch(client):
    """Newest in-progress row that is still part of the current session."""
    profiles = [client._profile_id]
    for index in client.profile_indexes():
        if index not in profiles:
            profiles.append(index)
    newest = None
    for profile_id in profiles:
        for row in client.watch_progress(profile_id):
            parsed = _parse_progress_row(row)
            if parsed is None:
                continue
            if newest is None or parsed["last_watched"] > newest["last_watched"]:
                newest = parsed
    if newest is None:
        return None
    age = datetime.now(timezone.utc).timestamp() - _epoch_seconds(
        newest["last_watched"],
    )
    if age > LIVE_VISIBLE_SECONDS:
        return None
    duration = _as_ms(newest["duration"])
    position = _as_ms(newest["position"])
    if duration and position / duration >= 0.9:
        return None
    newest["position_ms"] = position
    newest["duration_ms"] = duration or None
    newest["watching"] = age <= LIVE_WATCHING_SECONDS
    return newest


def _show_nuvio_watch(user, current):
    """Resolve the title and keep only this live row."""
    found = services.tmdb.find(current["imdb_id"], "imdb_id") or {}
    key = "movie_results" if current["kind"] == "movie" else "tv_results"
    rows = found.get(key) or []
    if not rows or rows[0].get("id") is None:
        logger.info("No TMDB id for Nuvio watch %s", current["imdb_id"])
        return
    media_type = (
        MediaTypes.MOVIE.value if current["kind"] == "movie" else MediaTypes.TV.value
    )
    upsert_live_playback(
        user=user,
        media_type=media_type,
        source=Sources.TMDB.value,
        media_id=str(rows[0]["id"]),
        position_ms=current["position_ms"],
        duration_ms=current["duration_ms"],
        status=(
            LivePlaybackStatus.WATCHING
            if current["watching"]
            else LivePlaybackStatus.PAUSED
        ),
        season_number=current["season"],
        episode_number=current["episode"],
        device_id="legacy",
        device_label="Ismeretlen eszköz",
    )
    # Sync only owns the legacy bucket; player-device strips stay.
    logger.info(
        "Nuvio sync live playback %s s%s e%s for %s",
        current["imdb_id"],
        current["season"],
        current["episode"],
        user.username,
    )


def _parse_progress_row(row):
    if not isinstance(row, dict):
        return None
    imdb_id = _imdb_id(row.get("content_id")) or _imdb_id(row.get("video_id"))
    if imdb_id is None:
        return None
    kind = _progress_kind(row.get("content_type"))
    season, episode = _season_episode(row, kind)
    if kind == "episode" and (season is None or episode is None):
        return None
    try:
        position = int(row.get("position") or 0)
        duration = int(row.get("duration") or 0)
        last_watched = int(row.get("last_watched") or 0)
    except (TypeError, ValueError):
        return None
    if last_watched <= 0 or position < 0:
        return None
    return {
        "imdb_id": imdb_id,
        "kind": "movie" if kind == "movie" else "episode",
        "season": season,
        "episode": episode,
        "position": position,
        "duration": duration,
        "last_watched": last_watched,
    }


def _imdb_id(value):
    text = str(value or "").strip().lower()
    head = text.split(":", 1)[0]
    if _IMDB_ID.match(head):
        return head
    return None


def _progress_kind(content_type):
    kind = str(content_type or "").strip().lower()
    if kind in {"movie", "movies"}:
        return "movie"
    return "episode"


def _season_episode(row, kind):
    if kind == "movie":
        return None, None
    season = _optional_int(row.get("season"))
    episode = _optional_int(row.get("episode"))
    if season is not None and episode is not None:
        return season, episode
    parts = str(row.get("video_id") or "").split(":")
    if len(parts) != 3:
        return season, episode
    return _optional_int(parts[1]), _optional_int(parts[2])


def _as_ms(value):
    if value <= 0:
        return 0
    if value < _MS_THRESHOLD:
        return value * 1000
    return value


def _epoch_seconds(value):
    if value > _EPOCH_MS_THRESHOLD:
        return value / 1000
    return float(value)


def importer(_identifier, user, mode):
    """Import movies and episodes for the user's saved Nuvio account."""
    return NuvioImporter(user, mode=mode).import_data()


def saved_login(user):
    """Return the stored email and profile. The password stays out of the page."""
    try:
        account = user.nuvio_account
        email = helpers.decrypt(account.email)
    except (NuvioAccount.DoesNotExist, InvalidToken):
        return None
    return {"email": email, "profile_id": account.profile_id}


def fill_saved_login(user, email, password):
    """Use the stored sign-in when the form leaves the password or email blank."""
    try:
        account = user.nuvio_account
        stored_email = helpers.decrypt(account.email)
        stored_password = helpers.decrypt(account.password)
    except (NuvioAccount.DoesNotExist, InvalidToken):
        return email, password
    return email or stored_email, password or stored_password


def save_account(user, email, password, profile_id):
    """Store encrypted Nuvio credentials. A different account restarts the cursor."""
    encrypted_email = helpers.encrypt(email)
    encrypted_password = helpers.encrypt(password)
    try:
        account = user.nuvio_account
    except NuvioAccount.DoesNotExist:
        return NuvioAccount.objects.create(
            user=user,
            email=encrypted_email,
            password=encrypted_password,
            profile_id=profile_id,
        )

    identity_changed = account.profile_id != profile_id
    try:
        identity_changed = identity_changed or helpers.decrypt(account.email) != email
    except InvalidToken:
        identity_changed = True

    account.email = encrypted_email
    account.password = encrypted_password
    account.profile_id = profile_id
    update_fields = ["email", "password", "profile_id"]
    if identity_changed:
        account.cursor = None
        account.bootstrapped = False
        account.imported_ids = []
        account.permanent_ids = []
        update_fields.extend(
            ["cursor", "bootstrapped", "imported_ids", "permanent_ids"],
        )
    account.save(update_fields=update_fields)
    return account


class NuvioClient:
    """Talk to one Nuvio profile's watch history (read and optional write)."""

    def __init__(self, account):
        """Sign in with the encrypted password stored for this account."""
        self._account = account
        self._email = helpers.decrypt(account.email)
        self._password = helpers.decrypt(account.password)
        self._profile_id = account.profile_id
        self._access_token = None
        self._access_expires_at = 0.0

    def assert_profile(self):
        """Fail before any write when the selected profile does not exist."""
        payload = self._rpc("sync_pull_profiles", {})
        if not isinstance(payload, list):
            raise NuvioError("Nuvio profile list was not a list")
        indexes = {
            row.get("profile_index") for row in payload if isinstance(row, dict)
        }
        if self._profile_id not in indexes:
            raise NuvioError(f"Nuvio profile {self._profile_id} was not found")

    def history_cursor(self):
        """Return the current end of the Nuvio watch-history log."""
        payload = self._rpc(
            "sync_get_watched_items_delta_cursor",
            {"p_profile_id": self._profile_id},
        )
        if isinstance(payload, bool) or not isinstance(payload, (int, float)):
            raise NuvioError("Nuvio history cursor was not an integer")
        if isinstance(payload, float) and not payload.is_integer():
            raise NuvioError("Nuvio history cursor was not an integer")
        return int(payload)

    def iter_history(self):
        """Yield the full watch history, one page at a time.

        Any page RPC/network failure raises ``NuvioError`` so callers never treat
        a truncated pull as a complete snapshot.
        """
        page = 1
        while True:
            payload = self._rpc(
                "sync_pull_watched_items",
                {
                    "p_profile_id": self._profile_id,
                    "p_page": page,
                    "p_page_size": PAGE_SIZE,
                },
            )
            if not isinstance(payload, list):
                raise NuvioError("Nuvio watch history page was not a list")
            if not payload:
                return
            yield from payload
            if len(payload) < PAGE_SIZE:
                return
            page += 1

    def profile_indexes(self):
        """Return every profile index on this Nuvio account."""
        payload = self._rpc("sync_pull_profiles", {})
        if not isinstance(payload, list):
            raise NuvioError("Nuvio profile list was not a list")
        indexes = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            index = row.get("profile_index")
            if isinstance(index, bool) or not isinstance(index, int):
                continue
            indexes.append(index)
        return indexes

    def watch_progress(self, profile_id=None):
        """Return in-progress watches for one profile."""
        payload = self._rpc(
            "sync_pull_watch_progress",
            {
                "p_profile_id": self._profile_id if profile_id is None else profile_id,
                "p_limit": 200,
            },
        )
        if not isinstance(payload, list):
            raise NuvioError("Nuvio watch progress was not a list")
        return payload

    def iter_delta(self, since_event_id):
        """Yield watch-history changes after the saved cursor."""
        since = since_event_id or 0
        while True:
            payload = self._rpc(
                "sync_pull_watched_items_delta",
                {
                    "p_profile_id": self._profile_id,
                    "p_since_event_id": since,
                    "p_limit": PAGE_SIZE,
                },
            )
            if not isinstance(payload, list):
                raise NuvioError("Nuvio history delta was not a list")
            if not payload:
                return
            rows = sorted(payload, key=lambda row: int(row.get("event_id") or 0))
            highest = int(rows[-1].get("event_id") or 0)
            if highest <= since:
                raise NuvioError("Nuvio history delta did not advance the cursor")
            yield from rows
            since = highest
            if len(rows) < PAGE_SIZE:
                return

    def push_watched_items(self, items):
        """Upsert watched-history rows. Safe to retry the same items."""
        if not items:
            return
        self._rpc(
            "sync_push_watched_items",
            {
                "p_profile_id": self._profile_id,
                "p_items": items,
            },
        )

    def delete_watched_items(self, keys):
        """Delete watched-history rows by content keys. Safe to retry."""
        if not keys:
            return
        self._rpc(
            "sync_delete_watched_items",
            {
                "p_profile_id": self._profile_id,
                "p_keys": keys,
            },
        )

    def delete_watch_progress(self, progress_keys):
        """Delete continue-watching progress rows by progress_key. Safe to retry."""
        if not progress_keys:
            return
        self._rpc(
            "sync_delete_watch_progress",
            {
                "p_profile_id": self._profile_id,
                "p_keys": list(progress_keys),
            },
        )

    def _rpc(self, name, body):
        try:
            return self._request(f"/rest/v1/rpc/{name}", body)
        except NuvioError as exc:
            if exc.status not in {401, 403}:
                raise
            self._access_token = None
            return self._request(f"/rest/v1/rpc/{name}", body)

    def _request(self, path, body):
        self._ensure_token()
        try:
            response = requests.post(
                NUVIO_BASE_URL + path,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "apikey": NUVIO_PUBLISHABLE_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=body,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise NuvioError("Nuvio request failed") from exc
        if response.status_code >= 400:
            raise NuvioError("Nuvio request failed", response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def _ensure_token(self):
        now = datetime.now(timezone.utc).timestamp()
        if self._access_token and now < self._access_expires_at - 60:
            return
        try:
            response = requests.post(
                f"{NUVIO_BASE_URL}/auth/v1/token?grant_type=password",
                headers={
                    "apikey": NUVIO_PUBLISHABLE_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"email": self._email, "password": self._password},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise NuvioError("Nuvio sign-in failed") from exc
        if response.status_code >= 400:
            raise NuvioError("Nuvio sign-in failed", response.status_code)
        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise NuvioError("Nuvio sign-in did not return an access token")
        self._access_token = token
        self._access_expires_at = datetime.now(timezone.utc).timestamp() + int(
            payload.get("expires_in") or 3600,
        )


class NuvioImporter:
    """Copy Nuvio watches onto this user's movies and episodes."""

    def __init__(self, user, client=None, mode="new", *, gate_upserts=False):
        """Load the saved account. Tests can pass a client that does not sign in."""
        self.user = user
        self.mode = "overwrite" if mode == "overwrite" else "new"
        # Periodic sync honors the mark-watched toggle; manual import always upserts.
        self.gate_upserts = gate_upserts
        try:
            self.account = user.nuvio_account
        except NuvioAccount.DoesNotExist as exc:
            msg = "Nuvio account is not configured."
            raise MediaImportError(msg) from exc
        self.client = client or NuvioClient(self.account)
        self.warnings = []
        self.created = {MediaTypes.MOVIE.value: 0, MediaTypes.EPISODE.value: 0}
        self.removed = {MediaTypes.MOVIE.value: 0, MediaTypes.EPISODE.value: 0}
        self._pending_account_fields = set()
        self._imported = set(self.account.imported_ids)
        self._permanent = set(self.account.permanent_ids)
        self._imdb_map = dict(self.account.imdb_map)
        self._watched_keys = set(self.account.watched_keys or [])
        self._previous_watched_keys = set(self._watched_keys)
        # While True, _apply keeps watched_keys in memory only; DB commit is deferred
        # until the full import (history pages + local ops + reconcile) succeeds.
        self._defer_watched_keys = False

    def import_data(self):
        """Read history, then later changes, and store the cursor when it is safe."""
        self._previous_watched_keys = set(self.account.watched_keys or [])
        self._watched_keys = set(self._previous_watched_keys)
        self._defer_watched_keys = True
        try:
            self.client.assert_profile()
            remote_keys, snapshot_complete = self._replay_history()
            self._delta()
            # Snapshot reconcile only after every history page and local apply succeeded.
            if (
                self.user.nuvio_sync_mark_unplayed_enabled
                and snapshot_complete
            ):
                self._reconcile_unwatched(remote_keys)
            if snapshot_complete:
                self._commit_watched_keys(remote_keys)
            else:
                self._restore_watched_keys()
        except NuvioError as exc:
            self._restore_watched_keys()
            self._raise_import_error(exc)
        except Exception:
            self._restore_watched_keys()
            raise
        finally:
            self._defer_watched_keys = False

        counts = {
            media_type: count for media_type, count in self.created.items() if count
        }
        removed_counts = {
            media_type: count for media_type, count in self.removed.items() if count
        }
        return counts, "\n".join(self.warnings), removed_counts

    def sync_delta(self):
        """Apply only the watched-history delta for interactive sync."""
        if not self.account.bootstrapped or self.account.cursor is None:
            msg = "Nuvio history has not been imported yet."
            raise MediaImportError(msg)
        try:
            self.client.assert_profile()
            self._delta()
        except NuvioError as exc:
            self._raise_import_error(exc)
        counts = {
            media_type: count for media_type, count in self.created.items() if count
        }
        return counts, "\n".join(self.warnings)

    def _raise_import_error(self, exc):
        if exc.status in {401, 403}:
            msg = "Nuvio sign-in failed."
            raise MediaImportError(msg) from exc
        if exc.status in _BLOCKING_STATUS:
            msg = (
                "Nuvio could not be reached. "
                "The import will continue on the next run."
            )
            raise MediaImportError(msg) from exc
        raise MediaImportError(str(exc)) from exc

    def _replay_history(self):
        """Check the full watch history and add anything missing locally.

        Bootstrap follows Nuvio's cursor-before-snapshot order so changes that
        land while pages are downloading are not lost:

        1. Capture ``sync_get_watched_items_delta_cursor`` first.
        2. Pull every ``sync_pull_watched_items`` page.
        3. Let ``_delta`` apply events after that captured cursor.

        Capturing the tip *after* the snapshot would skip mid-bootstrap events
        that never appeared in an already-fetched page. On later imports, keep
        the saved cursor (do not jump to tip) so delete events remain visible.

        Returns ``(remote_tmdb_keys, snapshot_complete)``. ``snapshot_complete``
        is True only when every history page was fetched and every row that
        should map to TMDB did. ``watched_keys`` is not written here — the
        caller commits them only after delta/reconcile succeed.
        """
        # Cursor BEFORE snapshot (Nuvio bootstrap order). Never move this below
        # iter_history — a post-snapshot tip would open a gap for live changes.
        tip = self.client.history_cursor()
        first_bootstrap = not self.account.bootstrapped
        if first_bootstrap:
            logger.info(
                "Nuvio bootstrap cursor captured before snapshot tip=%s user=%s",
                tip,
                self.user.id,
            )
        remote_keys = set()
        unmapped = 0
        logger.info("Nuvio import started user=%s", self.user.id)
        # iter_history raises on mid-pagination API errors; that aborts before
        # snapshot_complete can become True.
        for index, row in enumerate(self.client.iter_history(), start=1):
            if not self._apply(row, operation="upsert", event_id=None):
                self._flush_progress()
                msg = (
                    "Nuvio import stopped before the history snapshot finished. "
                    "It will continue on the next run."
                )
                raise MediaImportError(msg)
            key = self._watched_key_from_row(row)
            if key:
                remote_keys.add(key)
            elif self._row_expects_tmdb_key(row):
                unmapped += 1
            if index % 25 == 0:
                self._log_progress(index)
        self._flush_progress()
        snapshot_complete = unmapped == 0
        if not snapshot_complete:
            logger.warning(
                "Nuvio snapshot incomplete (%s rows without TMDB key); "
                "keeping prior watched_keys and skipping reconcile",
                unmapped,
            )
            if first_bootstrap:
                self.account.cursor = tip
                self.account.bootstrapped = True
                self._save_account(["cursor", "bootstrapped"])
            return remote_keys, False

        if first_bootstrap:
            self.account.cursor = tip
            self.account.bootstrapped = True
            self._save_account(["cursor", "bootstrapped"])
            logger.info(
                "Nuvio bootstrap snapshot done tip=%s remote_keys=%s user=%s; "
                "delta will cover changes after tip",
                tip,
                len(remote_keys),
                self.user.id,
            )
        logger.info(
            "Nuvio import history checked (%s remote TMDB keys) user=%s",
            len(remote_keys),
            self.user.id,
        )
        return remote_keys, True

    def _commit_watched_keys(self, remote_keys):
        """Persist the new snapshot keys after a fully successful import."""
        self._watched_keys = set(remote_keys)
        self.account.watched_keys = sorted(remote_keys)
        self._save_account(["watched_keys"])

    def _restore_watched_keys(self):
        """Keep the last good snapshot when this import did not finish cleanly."""
        self._watched_keys = set(self._previous_watched_keys)
        self.account.watched_keys = sorted(self._previous_watched_keys)
        self._save_account(["watched_keys"])

    def _note_watched_key(self, key, *, present):
        """Update the in-memory watch set; persist only when not deferred."""
        if not key:
            return
        if present:
            if key in self._watched_keys:
                return
            self._watched_keys.add(key)
        else:
            if key not in self._watched_keys:
                return
            self._watched_keys.discard(key)
        if self._defer_watched_keys:
            return
        self.account.watched_keys = sorted(self._watched_keys)
        self._save_account(["watched_keys"])

    def _reconcile_unwatched(self, remote_keys):
        """Remove Nuvio-managed local watches missing from a complete snapshot.

        Eligible keys are only those previously stored from a successful Nuvio
        snapshot (``watched_keys``). Other MediaTrail watches (Trakt, manual,
        etc.) are left alone even when absent from the remote snapshot.
        """
        managed = set(self._previous_watched_keys)
        stale = managed - set(remote_keys)
        logger.info(
            "Nuvio reconcile unwatched: managed=%s remote=%s stale=%s",
            len(managed),
            len(remote_keys),
            len(stale),
        )
        for key in stale:
            if self._delete_watched_key(key) == "delete":
                kind = key.split(":", 1)[0]
                if kind in self.removed:
                    self.removed[kind] += 1
                    logger.info("Nuvio reconcile removed managed key %s", key)

    def _watched_key_from_row(self, row):
        """Return a normalized TMDB watch key, or None if it cannot be resolved.

        IMDb and ``tmdb:`` content ids both resolve here so snapshot compare
        never treats the same title as missing under a different id form.
        """
        try:
            record = record_from_nuvio(row, operation="upsert", event_id=None)
        except RecordError:
            return None
        if record["source"] == "imdb":
            mapped = self._map_imdb(record)
            if not mapped:
                return None
            record = mapped
        if record["source"] != Sources.TMDB.value:
            return None
        return self._watched_key_from_record(record)

    def _row_expects_tmdb_key(self, row):
        """True when this history row should resolve to a TMDB watch key."""
        try:
            record = record_from_nuvio(row, operation="upsert", event_id=None)
        except RecordError:
            return False
        return record["kind"] in {
            MediaTypes.MOVIE.value,
            MediaTypes.EPISODE.value,
        }

    def _watched_key_from_record(self, record):
        if record["kind"] == MediaTypes.MOVIE.value:
            return f"movie:{record['media_id']}"
        return (
            f"episode:{record['media_id']}:"
            f"{record['season']}:{record['episode']}"
        )

    def _delete_watched_key(self, key):
        parts = str(key).split(":")
        if len(parts) == 2 and parts[0] == "movie":
            return self._delete_movie(
                {
                    "media_id": parts[1],
                    "title": key,
                },
            )
        if len(parts) == 4 and parts[0] == "episode":
            return self._delete_episode(
                {
                    "media_id": parts[1],
                    "season": int(parts[2]),
                    "episode": int(parts[3]),
                    "title": key,
                },
            )
        return "missing"

    def _delta(self):
        """Apply every delta event; advance the cursor only if all succeed.

        Partial progress must not move ``account.cursor``, otherwise the next
        run would skip the failed event (and any after it that were already
        consumed in this pass).
        """
        since = self.account.cursor
        start_cursor = since
        last_applied = None
        applied = 0
        deletes = 0
        logger.info(
            "Nuvio delta starting from cursor=%s user=%s",
            since,
            self.user.id,
        )
        try:
            for row in self.client.iter_delta(since):
                event_id = row.get("event_id") if isinstance(row, dict) else None
                if event_id is None:
                    msg = (
                        "Nuvio import stopped on a failed record. "
                        "It will continue on the next run."
                    )
                    raise MediaImportError(msg)
                operation = str(row.get("operation") or "upsert")
                logger.info(
                    "Nuvio delta event_id=%s operation=%s content_id=%s "
                    "season=%s episode=%s user=%s",
                    event_id,
                    operation,
                    row.get("content_id"),
                    row.get("season"),
                    row.get("episode"),
                    self.user.id,
                )
                before_removed = dict(self.removed)
                if not self._apply(row, operation=operation, event_id=int(event_id)):
                    msg = (
                        "Nuvio import stopped on a failed record. "
                        "It will continue on the next run."
                    )
                    raise MediaImportError(msg)
                last_applied = int(event_id)
                applied += 1
                if operation == "delete":
                    deletes += sum(
                        self.removed.get(kind, 0) - before_removed.get(kind, 0)
                        for kind in self.removed
                    )
            self._flush_progress()
            if last_applied is not None and self.account.bootstrapped:
                self.account.cursor = last_applied
                self._save_account(["cursor"])
            logger.info(
                "Nuvio delta finished user=%s start_cursor=%s end_cursor=%s "
                "events=%s local_deletes=%s",
                self.user.id,
                start_cursor,
                self.account.cursor,
                applied,
                deletes,
            )
        except Exception:
            if self.account.cursor != start_cursor:
                self.account.cursor = start_cursor
                self._save_account(["cursor"])
            raise

    def _apply(self, row, *, operation, event_id):
        if not isinstance(row, dict):
            return False
        try:
            record = record_from_nuvio(row, operation=operation, event_id=event_id)
        except RecordError as exc:
            nuvio_id = _nuvio_id(row, event_id)
            if nuvio_id and nuvio_id in self._imported:
                return True
            logger.info("skip unsupported Nuvio record: %s", exc)
            self._remember(nuvio_id)
            return True

        nuvio_id = record["nuvio_id"]
        if nuvio_id and nuvio_id in self._permanent:
            logger.info(
                "Nuvio skip permanent id=%s content_id=%s operation=%s",
                nuvio_id,
                row.get("content_id"),
                record["operation"],
            )
            return True
        if record["source"] == "imdb":
            mapped = self._map_imdb(record)
            if mapped is False:
                return False
            if mapped is None:
                logger.info(
                    "Nuvio skip unmapped IMDb content_id=%s operation=%s",
                    row.get("content_id"),
                    record["operation"],
                )
                return True
            record = mapped
        if record["operation"] == "delete":
            if not self.user.nuvio_sync_mark_unplayed_enabled:
                logger.info(
                    "Nuvio skip delete; mark-unplayed sync off content_id=%s "
                    "season=%s episode=%s",
                    row.get("content_id"),
                    row.get("season"),
                    row.get("episode"),
                )
                self._remember(nuvio_id)
                return True
            if self.gate_upserts and self._is_echo(row):
                logger.info(
                    "Nuvio skip outbound-echo delete content_id=%s "
                    "season=%s episode=%s",
                    row.get("content_id"),
                    row.get("season"),
                    row.get("episode"),
                )
                self._remember(nuvio_id)
                return True
            try:
                action = self._delete(record)
            except Exception:
                logger.exception("Nuvio delete failed for %s", record["title"])
                return False
            self._remember(nuvio_id)
            if action == "delete":
                self.removed[record["kind"]] += 1
                self._note_watched_key(
                    self._watched_key_from_record(record),
                    present=False,
                )
                logger.info(
                    "Nuvio sync deleted %s: %s (media_id=%s season=%s episode=%s)",
                    record["kind"],
                    record["title"],
                    record.get("media_id"),
                    record.get("season"),
                    record.get("episode"),
                )
            else:
                logger.warning(
                    "Nuvio delete found no local row content_id=%s media_id=%s "
                    "season=%s episode=%s",
                    row.get("content_id"),
                    record.get("media_id"),
                    record.get("season"),
                    record.get("episode"),
                )
            return True
        if record["operation"] != "upsert":
            return True
        if self.gate_upserts and not self.user.nuvio_sync_mark_played_enabled:
            logger.info(
                "Nuvio skip upsert; mark-played sync off content_id=%s "
                "season=%s episode=%s",
                row.get("content_id"),
                row.get("season"),
                row.get("episode"),
            )
            self._remember(nuvio_id)
            return True
        if self.gate_upserts and self._is_echo(row):
            logger.info(
                "Nuvio skip outbound-echo upsert content_id=%s "
                "season=%s episode=%s",
                row.get("content_id"),
                row.get("season"),
                row.get("episode"),
            )
            self._remember(nuvio_id)
            return True

        try:
            action = self._write(record)
        except services.ProviderAPIError as exc:
            if exc.status_code in {None, 429, 500, 502, 503, 504}:
                logger.warning("Nuvio import paused on TMDB status %s", exc.status_code)
                return False
            self._permanent_skip(record, "not found in TMDB")
            return True
        except NuvioError:
            raise
        except Exception:
            logger.exception("Nuvio record failed for %s", record["title"])
            return False

        if action == "missing":
            self._permanent_skip(record, "not found in TMDB")
            return True
        self._remember(nuvio_id)
        if action in {"create", "update", "skip"}:
            self._note_watched_key(
                self._watched_key_from_record(record),
                present=True,
            )
        if action in {"create", "update", "skip"}:
            logger.info(
                "Nuvio import %s %s: %s (media_id=%s season=%s episode=%s)",
                action,
                record["kind"],
                record["title"],
                record.get("media_id"),
                record.get("season"),
                record.get("episode"),
            )
        if action in {"create", "update"}:
            self.created[record["kind"]] += 1
        return True

    def _is_echo(self, row):
        """Skip delta rows that match a recent outbound push or delete."""
        from integrations.nuvio_outbound import is_pending_outbound

        return is_pending_outbound(self.user.id, row)

    def _write(self, record):
        if record["kind"] == MediaTypes.MOVIE.value:
            return self._write_movie(record)
        return self._write_episode(record)

    def _delete(self, record):
        if record["kind"] == MediaTypes.MOVIE.value:
            return self._delete_movie(record)
        return self._delete_episode(record)

    def _delete_movie(self, record):
        media_id = str(record["media_id"])
        existing = (
            app.models.Movie.objects.filter(
                user=self.user,
                item__media_id=media_id,
                item__source=Sources.TMDB.value,
                item__media_type=MediaTypes.MOVIE.value,
            )
            .order_by("-end_date", "-created_at")
            .first()
        )
        if existing is None:
            return "missing"
        existing.delete()
        return "delete"

    def _delete_episode(self, record):
        media_id = str(record["media_id"])
        season_number = record["season"]
        episode_number = record["episode"]
        existing = (
            app.models.Episode.objects.filter(
                related_season__user=self.user,
                item__media_id=media_id,
                item__source=Sources.TMDB.value,
                item__media_type=MediaTypes.EPISODE.value,
                item__season_number=season_number,
                item__episode_number=episode_number,
            )
            .order_by("-end_date", "-created_at")
            .first()
        )
        if existing is None:
            return "missing"
        existing.delete()
        return "delete"

    def _write_movie(self, record):
        media_id = str(record["media_id"])
        existing = (
            app.models.Movie.objects.filter(
                user=self.user,
                item__media_id=media_id,
                item__source=Sources.TMDB.value,
                item__media_type=MediaTypes.MOVIE.value,
            )
            .order_by("-end_date", "-created_at")
            .first()
        )
        if existing:
            if self.mode != "overwrite":
                return "skip"
            existing.end_date = record["end_date"]
            existing.status = Status.COMPLETED.value
            existing.progress = 1
            existing._history_date = record["end_date"]
            existing.save()
            return "update"
        metadata = self._metadata(MediaTypes.MOVIE.value, media_id, record["title"])
        if metadata is None:
            return "missing"
        item = self._item(MediaTypes.MOVIE.value, media_id, metadata)
        movie = app.models.Movie(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
            progress=1,
            end_date=record["end_date"],
            notes="",
        )
        movie._history_date = record["end_date"]
        movie.save()
        return "create"

    def _write_episode(self, record):
        media_id = str(record["media_id"])
        season_number = record["season"]
        episode_number = record["episode"]
        existing = (
            app.models.Episode.objects.filter(
                related_season__user=self.user,
                item__media_id=media_id,
                item__source=Sources.TMDB.value,
                item__media_type=MediaTypes.EPISODE.value,
                item__season_number=season_number,
                item__episode_number=episode_number,
            )
            .order_by("-end_date", "-created_at")
            .first()
        )
        if existing:
            if self.mode != "overwrite":
                return "skip"
            existing.end_date = record["end_date"]
            existing._history_date = record["end_date"]
            self._save_episode(existing)
            return "update"

        tv = self._tv(media_id, record["title"])
        if tv is None:
            return "missing"
        season_metadata = self._metadata(
            MediaTypes.SEASON.value,
            media_id,
            record["title"],
            season_number,
        )
        if season_metadata is None:
            return "missing"
        episodes = season_metadata.get("episodes") or []
        if not any(episode.get("episode_number") == episode_number for episode in episodes):
            return "missing"
        season = self._season(tv, media_id, season_number, season_metadata)
        image = settings.IMG_NONE
        for episode in episodes:
            if episode.get("episode_number") == episode_number and episode.get("still_path"):
                image = f"https://image.tmdb.org/t/p/w500{episode['still_path']}"
                break
        item = self._item(
            MediaTypes.EPISODE.value,
            media_id,
            {"title": tv.item.title, "image": image},
            season_number,
            episode_number,
        )
        episode = app.models.Episode(
            item=item,
            related_season=season,
            end_date=record["end_date"],
            notes="",
        )
        episode._history_date = record["end_date"]
        self._save_episode(episode)
        self._update_season_status(season, episode_number, len(episodes))
        return "create"

    def _save_episode(self, episode):
        """Store the episode without the per-row metadata reload in Episode.save."""
        super(app.models.Episode, episode).save()

    def _update_season_status(self, season, episode_number, episode_count):
        """Mark a season from metadata already loaded for this episode."""
        if not episode_count:
            return
        target = (
            Status.COMPLETED.value
            if episode_number == episode_count
            else Status.IN_PROGRESS.value
        )
        if season.status == target:
            return
        season.status = target
        bulk_update_with_history([season], app.models.Season, ["status"])

    def _log_progress(self, index):
        self._flush_progress()
        logger.info(
            "Nuvio import progress: %s rows, %s movies, %s episodes",
            index,
            self.created[MediaTypes.MOVIE.value],
            self.created[MediaTypes.EPISODE.value],
        )

    def _tv(self, media_id, title):
        existing = app.models.TV.objects.filter(
            user=self.user,
            item__media_id=media_id,
            item__source=Sources.TMDB.value,
            item__media_type=MediaTypes.TV.value,
        ).first()
        if existing:
            return existing
        metadata = self._metadata(MediaTypes.TV.value, media_id, title)
        if metadata is None:
            return None
        item = self._item(MediaTypes.TV.value, media_id, metadata)
        tv = app.models.TV(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            notes="",
        )
        app.models.TV.save_base(tv)
        return tv

    def _season(self, tv, media_id, season_number, metadata):
        existing = app.models.Season.objects.filter(
            user=self.user,
            item__media_id=media_id,
            item__source=Sources.TMDB.value,
            item__media_type=MediaTypes.SEASON.value,
            item__season_number=season_number,
        ).first()
        if existing:
            return existing
        item = self._item(
            MediaTypes.SEASON.value,
            media_id,
            metadata,
            season_number,
        )
        season = app.models.Season(
            item=item,
            user=self.user,
            related_tv=tv,
            status=Status.IN_PROGRESS.value,
            notes="",
        )
        app.models.Season.save_base(season)
        return season

    def _metadata(self, media_type, media_id, title, season_number=None):
        kwargs = {}
        if season_number is not None:
            kwargs["season_numbers"] = [season_number]
        try:
            return services.get_media_metadata(
                media_type,
                media_id,
                Sources.TMDB.value,
                **kwargs,
            )
        except services.ProviderAPIError as exc:
            if exc.status_code == requests.codes.not_found:
                logger.info("TMDB has no %s %s for %s", media_type, media_id, title)
                return None
            raise

    def _item(self, media_type, media_id, metadata, season_number=None, episode_number=None):
        lookup = {
            "media_id": str(media_id),
            "source": Sources.TMDB.value,
            "media_type": media_type,
        }
        if season_number is not None:
            lookup["season_number"] = season_number
        if episode_number is not None:
            lookup["episode_number"] = episode_number
        item, _created = app.models.Item.objects.get_or_create(
            **lookup,
            defaults={
                "title": metadata.get("title") or "Untitled",
                "image": metadata.get("image") or settings.IMG_NONE,
            },
        )
        return item

    def _map_imdb(self, record):
        imdb_id = record["media_id"]
        if imdb_id not in self._imdb_map:
            if not settings.TMDB_API:
                self._imdb_map[imdb_id] = ""
                self.account.imdb_map = dict(self._imdb_map)
                self._save_account(["imdb_map"])
                self._permanent_skip(record, "needs a TMDB API key")
                return None
            try:
                payload = app.providers.tmdb.find(imdb_id, "imdb_id")
            except services.ProviderAPIError as exc:
                if exc.status_code in {None, 429, 500, 502, 503, 504}:
                    return False
                payload = {}
            self._imdb_map[imdb_id] = _pick_tmdb_id(payload, record["kind"]) or ""
            self.account.imdb_map = dict(self._imdb_map)
            self._save_account(["imdb_map"])
        tmdb_id = self._imdb_map[imdb_id]
        if not tmdb_id:
            self._permanent_skip(record, "not found in TMDB")
            return None
        mapped = dict(record)
        mapped["source"] = Sources.TMDB.value
        mapped["media_id"] = str(tmdb_id)
        return mapped

    def _permanent_skip(self, record, reason):
        title = record["title"]
        self.warnings.append(f"{title}: {reason}.")
        nuvio_id = record["nuvio_id"]
        if nuvio_id and nuvio_id not in self._permanent:
            self._permanent.add(nuvio_id)
            self.account.permanent_ids = sorted(self._permanent)
            self._save_account(["permanent_ids"])

    def _remember(self, nuvio_id):
        if not nuvio_id or nuvio_id in self._imported:
            return
        self._imported.add(nuvio_id)
        self.account.imported_ids = sorted(self._imported)
        self._pending_account_fields.add("imported_ids")

    def _flush_progress(self):
        if not self._pending_account_fields:
            return
        self._save_account(sorted(self._pending_account_fields))
        self._pending_account_fields.clear()

    def _save_account(self, fields):
        self.account.save(update_fields=fields)


def record_from_nuvio(row, *, operation, event_id):
    """Turn one Nuvio history object into the fields this import stores."""
    content_id = str(row.get("content_id") or "").strip()
    content_type = str(row.get("content_type") or "").lower()
    title = str(row.get("title") or content_id or "untitled")
    source, media_id, extra = _split_content_id(content_id, title)
    season = _optional_int(row.get("season"))
    episode = _optional_int(row.get("episode"))
    if season is None and episode is None and len(extra) == 2:
        season = _optional_int(extra[0])
        episode = _optional_int(extra[1])

    watched_at = row.get("watched_at")
    end_date = None
    if isinstance(watched_at, (int, float)) and not isinstance(watched_at, bool):
        end_date = datetime.fromtimestamp(int(watched_at) / 1000, tz=timezone.utc)
    elif operation != "delete":
        raise RecordError(f"missing watched_at for {title}")
    nuvio_id = _nuvio_id(row, event_id)

    if content_type == "movie":
        return {
            "kind": MediaTypes.MOVIE.value,
            "source": source,
            "media_id": media_id,
            "season": None,
            "episode": None,
            "end_date": end_date,
            "title": title,
            "operation": operation,
            "nuvio_id": nuvio_id,
        }
    if content_type == "series":
        if season is None or episode is None:
            raise RecordError(f"missing season or episode for {title}")
        return {
            "kind": MediaTypes.EPISODE.value,
            "source": source,
            "media_id": media_id,
            "season": season,
            "episode": episode,
            "end_date": end_date,
            "title": title,
            "operation": operation,
            "nuvio_id": nuvio_id,
        }
    raise RecordError(f"unsupported content type for {title}")


def _nuvio_id(row, event_id):
    raw = row.get("id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, int) and not isinstance(raw, bool):
        return str(raw)
    if event_id is not None:
        return f"event:{event_id}"
    return None


def _split_content_id(content_id, title):
    if not content_id:
        raise RecordError(f"unsupported content id {content_id!r} for {title}")
    parts = content_id.split(":")
    if parts[0].lower() == "imdb":
        parts = parts[1:]
    if not parts or not parts[0]:
        raise RecordError(f"unsupported content id {content_id!r} for {title}")
    head, extra = parts[0], parts[1:]
    if head.lower() == "tmdb":
        if not extra or not extra[0]:
            raise RecordError(f"missing tmdb id for {title}")
        return Sources.TMDB.value, extra[0], extra[1:]
    if _IMDB_ID.match(head):
        return "imdb", head.lower(), extra
    raise RecordError(f"unsupported content id {content_id!r} for {title}")


def _optional_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _pick_tmdb_id(payload, kind):
    if not isinstance(payload, dict):
        return None
    movies = payload.get("movie_results") or []
    shows = payload.get("tv_results") or []
    order = (movies, shows) if kind == MediaTypes.MOVIE.value else (shows, movies)
    for bucket in order:
        if isinstance(bucket, list) and bucket and isinstance(bucket[0], dict):
            found = bucket[0].get("id")
            if found is not None:
                return str(found)
    return None
