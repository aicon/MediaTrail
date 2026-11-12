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


def _metadata(media_type, media_id, source, season_numbers=None, episode_number=None):
    if media_type == "tv_with_seasons":
        return {
            "season/1": {
                "episodes": [{"episode_number": 1, "still_path": None}],
            },
        }
    if media_type == MediaTypes.TV.value:
        return {"title": "Show", "image": "https://example.test/show.jpg"}
    if media_type == MediaTypes.SEASON.value:
        return {
            "title": "Show",
            "image": "https://example.test/season.jpg",
            "episodes": [{"episode_number": 1, "still_path": None}],
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
            return nuvio.NuvioImporter(self.user, client).import_data()

    def test_creates_missing_movie_and_saves_cursor(self):
        counts, warnings = self._run(
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
        counts, _warnings = self._run(
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
        counts, _warnings = self._run(FakeNuvio(history))
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
