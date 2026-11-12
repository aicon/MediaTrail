from datetime import datetime, timezone
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import TV, Episode, Item, MediaTypes, Movie, Sources, Status
from app.providers.services import ProviderAPIError
from integrations.imports import helpers, nuvio
from integrations.models import NuvioAccount


WATCHED_AT = 1_711_600_000_000


def _history(content_id, content_type, title, watched_at=WATCHED_AT, **extra):
    row = {
        "id": extra.pop("nuvio_id", content_id),
        "content_id": content_id,
        "content_type": content_type,
        "title": title,
        "watched_at": watched_at,
    }
    row.update(extra)
    return row


class FakeNuvio:
    """In-memory Nuvio history. Does not sign in."""

    def __init__(self, history=None, delta=None, cursor=10):
        self.history = history or []
        self.delta = delta or []
        self.cursor = cursor

    def assert_profile(self):
        return None

    def history_cursor(self):
        return self.cursor

    def iter_history(self):
        yield from self.history

    def iter_delta(self, _since):
        yield from self.delta


class HistoryPageFailNuvio(FakeNuvio):
    """Yield some history rows, then fail like a mid-pagination API error."""

    def __init__(self, history, fail_after, cursor=10):
        super().__init__(history=history, cursor=cursor)
        self.fail_after = fail_after

    def iter_history(self):
        for index, row in enumerate(self.history):
            if index >= self.fail_after:
                raise nuvio.NuvioError("Nuvio request failed", 503)
            yield row


class DeltaFailNuvio(FakeNuvio):
    """Complete history pull, then fail while reading the delta."""

    def iter_delta(self, _since):
        raise nuvio.NuvioError("Nuvio request failed", 503)


def _metadata(media_type, media_id, source, season_numbers=None, episode_number=None):
    if media_type == "tv_with_seasons":
        seasons = season_numbers or [1]
        return {
            f"season/{number}": {
                "episodes": [
                    {"episode_number": ep, "still_path": None}
                    for ep in range(1, 25)
                ],
            }
            for number in seasons
        }
    if media_type == MediaTypes.TV.value:
        return {"title": "Show", "image": "https://example.test/show.jpg"}
    if media_type == MediaTypes.SEASON.value:
        return {
            "title": "Show",
            "image": "https://example.test/season.jpg",
            "episodes": [
                {"episode_number": ep, "still_path": None}
                for ep in range(1, 25)
            ],
        }
    if media_type == MediaTypes.MOVIE.value:
        return {
            "title": "Movie",
            "image": "https://example.test/movie.jpg",
            "max_progress": 1,
        }
    raise AssertionError(media_type)


class NuvioRecordTests(TestCase):
    """History rows map onto movies and episodes."""

    def test_movie_tmdb_id(self):
        record = nuvio.record_from_nuvio(
            _history("tmdb:550", "movie", "Fight Club"),
            operation="upsert",
            event_id=None,
        )
        self.assertEqual(record["kind"], MediaTypes.MOVIE.value)
        self.assertEqual(record["media_id"], "550")
        self.assertEqual(
            record["end_date"],
            datetime.fromtimestamp(WATCHED_AT / 1000, tz=timezone.utc),
        )

    def test_episode_imdb_id(self):
        record = nuvio.record_from_nuvio(
            _history("tt0903747", "series", "Breaking Bad", season=1, episode=1),
            operation="upsert",
            event_id=4,
        )
        self.assertEqual(record["source"], "imdb")
        self.assertEqual(record["media_id"], "tt0903747")
        self.assertEqual(record["season"], 1)
        self.assertEqual(record["episode"], 1)

    def test_unsupported_content_is_skipped_by_the_parser(self):
        with self.assertRaises(nuvio.RecordError):
            nuvio.record_from_nuvio(
                _history("kitsu:1", "movie", "Example"),
                operation="upsert",
                event_id=None,
            )

    def test_delete_without_watched_at(self):
        """Delete events identify by content keys; watched_at may be absent."""
        record = nuvio.record_from_nuvio(
            {
                "event_id": 12,
                "operation": "delete",
                "content_id": "tmdb:550",
                "content_type": "movie",
                "title": "Fight Club",
            },
            operation="delete",
            event_id=12,
        )
        self.assertEqual(record["operation"], "delete")
        self.assertEqual(record["media_id"], "550")
        self.assertIsNone(record["end_date"])


class NuvioImportTests(TestCase):
    """Missing movies and episodes are created. Deletes need the unwatched toggle."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("nuvio-user", password="secret")
        self.account = NuvioAccount.objects.create(
            user=self.user,
            email=helpers.encrypt("person@example.com"),
            password=helpers.encrypt("nuvio-secret"),
            profile_id=1,
        )

    def _run(self, client):
        with (
            patch("integrations.imports.nuvio.services.get_media_metadata", _metadata),
            patch("app.models.providers.services.get_media_metadata", _metadata),
        ):
            result = nuvio.NuvioImporter(self.user, client).import_data()
            # Support both legacy 2-tuple callers and (counts, warnings, removed).
            if len(result) == 2:
                counts, warnings = result
                return counts, warnings, {}
            return result

    def test_creates_missing_movie_and_saves_cursor(self):
        counts, warnings, _removed = self._run(
            FakeNuvio([_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")]),
        )
        self.assertEqual(counts[MediaTypes.MOVIE.value], 1)
        self.assertEqual(warnings, "")
        movie = Movie.objects.get(user=self.user)
        self.assertEqual(movie.item.media_id, "550")
        self.assertEqual(movie.status, Status.COMPLETED.value)
        self.account.refresh_from_db()
        self.assertTrue(self.account.bootstrapped)
        self.assertEqual(self.account.cursor, 10)
        self.assertEqual(self.account.imported_ids, ["m1"])

    def test_existing_movie_is_not_changed(self):
        item = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image="https://example.test/movie.jpg",
        )
        kept = datetime(2020, 1, 1, tzinfo=timezone.utc)
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
            progress=1,
            end_date=kept,
            notes="",
        )
        self._run(FakeNuvio([_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")]))
        movie = Movie.objects.get(user=self.user)
        self.assertEqual(movie.end_date, kept)
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)

    def test_overwrite_replaces_the_existing_movie_date(self):
        item = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image="https://example.test/movie.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
            progress=1,
            end_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            notes="keep this",
        )
        watched = datetime.fromtimestamp(WATCHED_AT / 1000, tz=timezone.utc)
        with patch("integrations.imports.nuvio.services.get_media_metadata", _metadata):
            nuvio.NuvioImporter(
                self.user,
                FakeNuvio([_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")]),
                mode="overwrite",
            ).import_data()
        movie = Movie.objects.get(user=self.user)
        self.assertEqual(movie.end_date, watched)
        self.assertEqual(movie.notes, "keep this")
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)

    def test_creates_missing_episode(self):
        counts, _warnings, _removed = self._run(
            FakeNuvio(
                [
                    _history(
                        "tmdb:1396",
                        "series",
                        "Breaking Bad",
                        season=1,
                        episode=1,
                        nuvio_id="e1",
                    ),
                ],
            ),
        )
        self.assertEqual(counts[MediaTypes.EPISODE.value], 1)
        episode = Episode.objects.get()
        self.assertEqual(episode.item.episode_number, 1)
        self.assertEqual(episode.item.season_number, 1)
        self.assertTrue(TV.objects.filter(user=self.user, item__media_id="1396").exists())

    def test_existing_episode_is_not_repeated(self):
        self._run(
            FakeNuvio(
                [
                    _history(
                        "tmdb:1396",
                        "series",
                        "Breaking Bad",
                        season=1,
                        episode=1,
                        nuvio_id="e1",
                    ),
                ],
            ),
        )
        self.account.refresh_from_db()
        self.account.bootstrapped = False
        self.account.cursor = None
        self.account.imported_ids = []
        self.account.save()
        self._run(
            FakeNuvio(
                [
                    _history(
                        "tmdb:1396",
                        "series",
                        "Breaking Bad",
                        season=1,
                        episode=1,
                        nuvio_id="e2",
                    ),
                ],
            ),
        )
        self.assertEqual(Episode.objects.count(), 1)

    def test_removed_episode_is_imported_again(self):
        history = [
            _history(
                "tmdb:1396",
                "series",
                "Breaking Bad",
                season=1,
                episode=1,
                nuvio_id="e1",
            ),
        ]
        self._run(FakeNuvio(history))
        Episode.objects.all().delete()
        counts, _warnings, _removed = self._run(FakeNuvio(history))
        self.assertEqual(counts[MediaTypes.EPISODE.value], 1)
        self.assertEqual(Episode.objects.count(), 1)

    def test_delete_does_not_remove_media_when_toggle_off(self):
        self._run(FakeNuvio([_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")]))
        self._run(
            FakeNuvio(
                delta=[
                    {
                        "event_id": 11,
                        "operation": "delete",
                        "id": "m1-delete",
                        "content_id": "tmdb:550",
                        "content_type": "movie",
                        "title": "Fight Club",
                        "watched_at": WATCHED_AT,
                    },
                ],
            ),
        )
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)

    def test_delete_removes_media_when_toggle_on(self):
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        self._run(FakeNuvio([_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")]))
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)
        self._run(
            FakeNuvio(
                delta=[
                    {
                        "event_id": 11,
                        "operation": "delete",
                        "id": "m1-delete",
                        "content_id": "tmdb:550",
                        "content_type": "movie",
                        "title": "Fight Club",
                        "watched_at": WATCHED_AT,
                    },
                ],
            ),
        )
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 0)

    def test_reimport_applies_delete_even_when_tip_cursor_passed_event(self):
        """Regression: replay must not jump the cursor past pending deletes."""
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        self._run(
            FakeNuvio(
                [_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                cursor=10,
            ),
        )
        self.account.refresh_from_db()
        self.assertEqual(self.account.cursor, 10)
        self._run(
            FakeNuvio(
                history=[],
                delta=[
                    {
                        "event_id": 11,
                        "operation": "delete",
                        "id": "m1-delete",
                        "content_id": "tmdb:550",
                        "content_type": "movie",
                        "title": "Fight Club",
                        "watched_at": WATCHED_AT,
                    },
                ],
                cursor=11,
            ),
        )
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 0)

    def test_reconcile_removes_episode_missing_from_snapshot(self):
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        history = [
            _history(
                "tmdb:1532",
                "series",
                "Starsky",
                season=2,
                episode=21,
                nuvio_id="e21",
            ),
            _history(
                "tmdb:1532",
                "series",
                "Starsky",
                season=2,
                episode=20,
                nuvio_id="e20",
            ),
        ]
        counts, _warnings, removed = self._run(FakeNuvio(history, cursor=5))
        self.assertEqual(Episode.objects.count(), 2)
        self.assertEqual(removed, {})
        self.account.refresh_from_db()
        self.assertIn("episode:1532:2:21", self.account.watched_keys)
        # Unrelated local watch must survive reconcile.
        other = Item.objects.create(
            media_id="999",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Local Only",
            image="https://example.test/other.jpg",
        )
        with patch("app.models.providers.services.get_media_metadata", _metadata):
            Movie.objects.create(
                item=other,
                user=self.user,
                status=Status.COMPLETED.value,
                progress=1,
                end_date=datetime.now(timezone.utc),
            )
        # Nuvio unwatched E21; snapshot only has E20. Cursor tip already past deletes.
        _counts, _warnings, removed = self._run(
            FakeNuvio(
                [
                    _history(
                        "tmdb:1532",
                        "series",
                        "Starsky",
                        season=2,
                        episode=20,
                        nuvio_id="e20",
                    ),
                ],
                cursor=99,
            ),
        )
        seasons_eps = {
            (ep.item.season_number, ep.item.episode_number)
            for ep in Episode.objects.all()
        }
        self.assertEqual(seasons_eps, {(2, 20)})
        self.assertEqual(removed.get(MediaTypes.EPISODE.value), 1)
        self.assertTrue(Movie.objects.filter(user=self.user, item__media_id="999").exists())

    def test_reconcile_skips_incomplete_snapshot(self):
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        self._run(
            FakeNuvio(
                [_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                cursor=5,
            ),
        )
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)
        # Incomplete: rows are present but cannot resolve to TMDB keys.
        # An empty history is a valid complete snapshot and must not be used here.
        with patch.object(
            nuvio.NuvioImporter,
            "_watched_key_from_row",
            return_value=None,
        ), patch.object(
            nuvio.NuvioImporter,
            "_row_expects_tmdb_key",
            return_value=True,
        ):
            _counts, _warnings, removed = self._run(
                FakeNuvio(
                    history=[
                        _history("tmdb:550", "movie", "Fight Club", nuvio_id="m1"),
                    ],
                    cursor=99,
                ),
            )
        self.assertEqual(removed, {})
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)
        self.account.refresh_from_db()
        self.assertIn("movie:550", self.account.watched_keys)

    def test_reconcile_normalizes_imdb_content_id_to_tmdb_key(self):
        """Same title via tt… must not look missing against a prior tmdb: key."""
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        self._run(
            FakeNuvio(
                [_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                cursor=5,
            ),
        )
        self.account.refresh_from_db()
        self.assertIn("movie:550", self.account.watched_keys)
        self.account.imdb_map = {"tt0137523": "550"}
        self.account.save(update_fields=["imdb_map"])
        _counts, _warnings, removed = self._run(
            FakeNuvio(
                [_history("tt0137523", "movie", "Fight Club", nuvio_id="m1")],
                cursor=5,
            ),
        )
        self.assertEqual(removed, {})
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)
        self.account.refresh_from_db()
        self.assertEqual(self.account.watched_keys, ["movie:550"])

    def test_history_page_error_keeps_prior_watched_keys(self):
        """A mid-pagination API error must not reconcile or replace watched_keys."""
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        self._run(
            FakeNuvio(
                [_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                cursor=5,
            ),
        )
        self.account.refresh_from_db()
        self.assertEqual(self.account.watched_keys, ["movie:550"])
        with self.assertRaises(nuvio.MediaImportError):
            self._run(
                HistoryPageFailNuvio(
                    history=[
                        _history("tmdb:551", "movie", "Other", nuvio_id="m2"),
                        _history("tmdb:552", "movie", "Later", nuvio_id="m3"),
                    ],
                    fail_after=1,
                    cursor=99,
                ),
            )
        self.account.refresh_from_db()
        self.assertEqual(self.account.watched_keys, ["movie:550"])
        self.assertTrue(Movie.objects.filter(user=self.user, item__media_id="550").exists())

    def test_delta_error_keeps_prior_watched_keys(self):
        """watched_keys updates only after history, delta, and reconcile succeed."""
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        self._run(
            FakeNuvio(
                [_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                cursor=5,
            ),
        )
        self.account.refresh_from_db()
        prior = list(self.account.watched_keys)
        # Empty remote history would delete 550 if keys were committed before delta.
        with self.assertRaises(nuvio.MediaImportError):
            self._run(DeltaFailNuvio(history=[], cursor=99))
        self.account.refresh_from_db()
        self.assertEqual(self.account.watched_keys, prior)
        self.assertEqual(self.account.cursor, 5)
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)

    def test_delta_cursor_advances_only_after_all_events_succeed(self):
        """A mid-delta apply failure must leave the cursor at the run start."""
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        self._run(
            FakeNuvio(
                [_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                cursor=5,
            ),
        )
        self.account.refresh_from_db()
        self.assertEqual(self.account.cursor, 5)
        original_apply = nuvio.NuvioImporter._apply

        def fail_on_second(importer, row, *, operation, event_id):
            if event_id == 12:
                return False
            return original_apply(
                importer, row, operation=operation, event_id=event_id,
            )

        with patch.object(nuvio.NuvioImporter, "_apply", fail_on_second):
            with self.assertRaises(nuvio.MediaImportError):
                self._run(
                    FakeNuvio(
                        history=[
                            _history("tmdb:550", "movie", "Fight Club", nuvio_id="m1"),
                        ],
                        delta=[
                            {
                                "event_id": 11,
                                "operation": "upsert",
                                "id": "m2",
                                "content_id": "tmdb:551",
                                "content_type": "movie",
                                "title": "Other",
                                "watched_at": WATCHED_AT,
                            },
                            {
                                "event_id": 12,
                                "operation": "upsert",
                                "id": "m3",
                                "content_id": "tmdb:552",
                                "content_type": "movie",
                                "title": "Later",
                                "watched_at": WATCHED_AT,
                            },
                        ],
                        cursor=99,
                    ),
                )
        self.account.refresh_from_db()
        self.assertEqual(self.account.cursor, 5)

    def test_delta_cursor_advances_when_all_events_succeed(self):
        self._run(
            FakeNuvio(
                [_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                cursor=5,
            ),
        )
        self._run(
            FakeNuvio(
                history=[_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                delta=[
                    {
                        "event_id": 11,
                        "operation": "upsert",
                        "id": "m2",
                        "content_id": "tmdb:551",
                        "content_type": "movie",
                        "title": "Other",
                        "watched_at": WATCHED_AT,
                    },
                    {
                        "event_id": 12,
                        "operation": "upsert",
                        "id": "m3",
                        "content_id": "tmdb:552",
                        "content_type": "movie",
                        "title": "Later",
                        "watched_at": WATCHED_AT,
                    },
                ],
                cursor=99,
            ),
        )
        self.account.refresh_from_db()
        self.assertEqual(self.account.cursor, 12)
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 3)

    def test_history_apply_failure_keeps_prior_watched_keys(self):
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        self._run(
            FakeNuvio(
                [_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")],
                cursor=5,
            ),
        )
        original_apply = nuvio.NuvioImporter._apply

        def fail_second(importer, row, *, operation, event_id):
            if row.get("id") == "m2":
                return False
            return original_apply(importer, row, operation=operation, event_id=event_id)

        with patch.object(nuvio.NuvioImporter, "_apply", fail_second):
            with self.assertRaises(nuvio.MediaImportError):
                self._run(
                    FakeNuvio(
                        history=[
                            _history("tmdb:550", "movie", "Fight Club", nuvio_id="m1"),
                            _history("tmdb:551", "movie", "Other", nuvio_id="m2"),
                        ],
                        cursor=99,
                    ),
                )
        self.account.refresh_from_db()
        self.assertEqual(self.account.watched_keys, ["movie:550"])

    def test_delete_removes_episode_when_toggle_on(self):
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        history = [
            _history(
                "tmdb:1396",
                "series",
                "Breaking Bad",
                season=1,
                episode=1,
                nuvio_id="e1",
            ),
        ]
        self._run(FakeNuvio(history))
        self.assertEqual(Episode.objects.count(), 1)
        self._run(
            FakeNuvio(
                delta=[
                    {
                        "event_id": 21,
                        "operation": "delete",
                        "id": "e1-delete",
                        "content_id": "tmdb:1396",
                        "content_type": "series",
                        "title": "Breaking Bad S01E01",
                        "season": 1,
                        "episode": 1,
                    },
                ],
            ),
        )
        self.assertEqual(Episode.objects.count(), 0)

    def test_sync_delta_skips_upsert_when_played_toggle_off(self):
        self._run(FakeNuvio([_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")]))
        self.account.refresh_from_db()
        self.assertTrue(self.account.bootstrapped)
        client = FakeNuvio(
            delta=[
                {
                    "event_id": 30,
                    "operation": "upsert",
                    "id": "m2",
                    "content_id": "tmdb:551",
                    "content_type": "movie",
                    "title": "Other",
                    "watched_at": WATCHED_AT,
                },
            ],
        )
        with (
            patch("integrations.imports.nuvio.services.get_media_metadata", _metadata),
            patch("app.models.providers.services.get_media_metadata", _metadata),
        ):
            nuvio.NuvioImporter(
                self.user,
                client,
                gate_upserts=True,
            ).sync_delta()
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)

    def test_tmdb_failure_keeps_the_cursor_unsaved(self):
        response = Mock(status_code=503, text="unavailable")
        error = requests.HTTPError("unavailable")
        error.response = response

        def fail_metadata(*_args, **_kwargs):
            raise ProviderAPIError("tmdb", error)

        client = FakeNuvio([_history("tmdb:550", "movie", "Fight Club", nuvio_id="m1")])
        with (
            patch("integrations.imports.nuvio.services.get_media_metadata", fail_metadata),
            self.assertRaises(nuvio.MediaImportError),
        ):
            nuvio.NuvioImporter(self.user, client).import_data()
        self.account.refresh_from_db()
        self.assertFalse(self.account.bootstrapped)
        self.assertIsNone(self.account.cursor)
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 0)

    def test_password_is_stored_encrypted(self):
        self.client.force_login(self.user)
        with patch("integrations.tasks.import_nuvio.delay") as queued:
            response = self.client.post(
                reverse("import_nuvio"),
                {
                    "email": "person@example.com",
                    "password": "plain-password",
                    "profile_id": "2",
                    "frequency": "once",
                    "time": "15:00",
                    "mode": "overwrite",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertEqual(helpers.decrypt(self.account.email), "person@example.com")
        self.assertEqual(helpers.decrypt(self.account.password), "plain-password")
        self.assertNotIn("plain-password", self.account.password)
        self.assertEqual(self.account.profile_id, 2)
        queued.assert_called_once()

    def test_blank_password_keeps_the_saved_login(self):
        self.client.force_login(self.user)
        nuvio.save_account(self.user, "person@example.com", "plain-password", 2)
        with patch("integrations.tasks.import_nuvio.delay") as queued:
            response = self.client.post(
                reverse("import_nuvio"),
                {
                    "email": "person@example.com",
                    "password": "",
                    "profile_id": "2",
                    "frequency": "once",
                    "time": "15:00",
                    "mode": "new",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertEqual(helpers.decrypt(self.account.password), "plain-password")
        queued.assert_called_once()

        page = self.client.get(reverse("import_data"))
        self.assertContains(page, "person@example.com")
        self.assertContains(page, 'value="2"')
        self.assertNotContains(page, "plain-password")
