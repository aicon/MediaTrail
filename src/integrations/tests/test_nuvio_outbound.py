from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from app.models import Episode, Item, MediaTypes, Movie, Season, Sources, Status
from integrations import nuvio_outbound
from integrations.imports import helpers
from integrations.models import NuvioAccount


class NuvioOutboundTests(TestCase):
    """Outbound watched sync builds import-matching keys and queues Celery work."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("out", password="secret")
        self.account = NuvioAccount.objects.create(
            user=self.user,
            email=helpers.encrypt("person@example.com"),
            password=helpers.encrypt("nuvio-secret"),
            profile_id=1,
            imdb_map={"tt0072567": "1532"},
        )
        self.movie_item = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image="https://example.test/m.jpg",
        )
        self.movie = Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.COMPLETED.value,
            progress=1,
            end_date=timezone.now(),
        )

    def test_enqueue_upsert_requires_toggle(self):
        with patch("integrations.tasks.push_nuvio_watched_item.delay") as delay:
            nuvio_outbound.enqueue_watched_upsert(self.user, self.movie)
            delay.assert_not_called()

    def test_enqueue_upsert_queues_tmdb_and_imdb_variants(self):
        self.user.nuvio_sync_mark_played_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_played_enabled"])
        self.account.imdb_map = {"tt0137523": "550"}
        self.account.save(update_fields=["imdb_map"])
        with patch("integrations.tasks.push_nuvio_watched_item.delay") as delay:
            nuvio_outbound.enqueue_watched_upsert(self.user, self.movie)
            delay.assert_called_once()
            user_id, items = delay.call_args.args
            self.assertEqual(user_id, self.user.id)
            content_ids = [item["content_id"] for item in items]
            self.assertEqual(
                content_ids,
                ["tmdb:550", "tt0137523", "imdb:tt0137523"],
            )

    def test_enqueue_delete_queues_episode_key_variants(self):
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        season_item = Item.objects.create(
            media_id="1532",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Starsky és Hutch",
            image="https://example.test/s.jpg",
            season_number=2,
        )
        season = Season.objects.create(
            item=season_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        ep_item = Item.objects.create(
            media_id="1532",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Pilot",
            image="https://example.test/e.jpg",
            season_number=2,
            episode_number=21,
        )
        episode = Episode.objects.create(
            item=ep_item,
            related_season=season,
            end_date=timezone.now(),
        )
        with patch("integrations.tasks.delete_nuvio_watched_item.delay") as delay:
            nuvio_outbound.enqueue_watched_delete(self.user, episode)
            delay.assert_called_once()
            _user_id, keys, progress_keys = delay.call_args.args
            self.assertEqual(
                keys,
                [
                    {"content_id": "tmdb:1532", "season": 2, "episode": 21},
                    {"content_id": "tt0072567", "season": 2, "episode": 21},
                    {"content_id": "imdb:tt0072567", "season": 2, "episode": 21},
                ],
            )
            self.assertEqual(
                progress_keys,
                [
                    "tmdb:1532_s2e21",
                    "tt0072567_s2e21",
                    "imdb:tt0072567_s2e21",
                ],
            )

    def test_pending_upsert_does_not_block_inbound_delete(self):
        """A recent watched push must not suppress a Nuvio unwatch for the same title."""
        self.user.nuvio_sync_mark_played_enabled = True
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(
            update_fields=[
                "nuvio_sync_mark_played_enabled",
                "nuvio_sync_mark_unplayed_enabled",
            ],
        )
        with patch("integrations.tasks.push_nuvio_watched_item.delay"):
            nuvio_outbound.enqueue_watched_upsert(self.user, self.movie)
        delete_row = {
            "operation": "delete",
            "content_id": "tmdb:550",
            "content_type": "movie",
            "title": "Fight Club",
        }
        self.assertFalse(nuvio_outbound.is_pending_outbound(self.user.id, delete_row))
        upsert_row = {
            "operation": "upsert",
            "content_id": "tmdb:550",
            "content_type": "movie",
            "title": "Fight Club",
            "watched_at": 1_711_600_000_000,
        }
        self.assertTrue(nuvio_outbound.is_pending_outbound(self.user.id, upsert_row))

    def test_pending_delete_does_not_block_inbound_upsert(self):
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        with patch("integrations.tasks.delete_nuvio_watched_item.delay"):
            nuvio_outbound.enqueue_watched_delete(self.user, self.movie)
        upsert_row = {
            "operation": "upsert",
            "content_id": "tmdb:550",
            "content_type": "movie",
            "title": "Fight Club",
            "watched_at": 1_711_600_000_000,
        }
        self.assertFalse(nuvio_outbound.is_pending_outbound(self.user.id, upsert_row))
        delete_row = {
            "operation": "delete",
            "content_id": "tmdb:550",
            "content_type": "movie",
            "title": "Fight Club",
        }
        self.assertTrue(nuvio_outbound.is_pending_outbound(self.user.id, delete_row))

    def test_client_push_handles_204(self):
        from integrations.imports import nuvio

        account = self.user.nuvio_account
        client = nuvio.NuvioClient(account)
        client._access_token = "token"
        client._access_expires_at = 9_999_999_999
        with patch("integrations.imports.nuvio.requests.post") as post:
            response = post.return_value
            response.status_code = 204
            response.content = b""
            client.push_watched_items(
                [
                    {
                        "content_id": "tmdb:550",
                        "content_type": "movie",
                        "title": "Fight Club",
                        "watched_at": 1_711_600_000_000,
                    },
                ],
            )
            post.assert_called_once()
            self.assertIn(
                "sync_push_watched_items",
                post.call_args.args[0],
            )
