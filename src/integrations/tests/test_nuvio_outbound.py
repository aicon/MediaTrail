from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from app.models import Episode, Item, MediaTypes, Movie, Sources, Status
from integrations.imports import helpers
from integrations.models import NuvioAccount
from integrations import nuvio_outbound


class NuvioOutboundTests(TestCase):
    """Outbound watched sync builds import-matching keys and queues Celery work."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user("out", password="secret")
        NuvioAccount.objects.create(
            user=self.user,
            email=helpers.encrypt("person@example.com"),
            password=helpers.encrypt("nuvio-secret"),
            profile_id=1,
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

    def test_enqueue_upsert_queues_tmdb_movie(self):
        self.user.nuvio_sync_mark_played_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_played_enabled"])
        with patch("integrations.tasks.push_nuvio_watched_item.delay") as delay:
            nuvio_outbound.enqueue_watched_upsert(self.user, self.movie)
            delay.assert_called_once()
            user_id, item = delay.call_args.args
            self.assertEqual(user_id, self.user.id)
            self.assertEqual(item["content_id"], "tmdb:550")
            self.assertEqual(item["content_type"], "movie")
            self.assertIn("watched_at", item)

    def test_enqueue_delete_queues_episode_key(self):
        self.user.nuvio_sync_mark_unplayed_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_unplayed_enabled"])
        season_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Breaking Bad",
            image="https://example.test/s.jpg",
            season_number=1,
        )
        from app.models import Season

        season = Season.objects.create(
            item=season_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        ep_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Pilot",
            image="https://example.test/e.jpg",
            season_number=1,
            episode_number=1,
        )
        episode = Episode.objects.create(
            item=ep_item,
            related_season=season,
            end_date=timezone.now(),
        )
        with patch("integrations.tasks.delete_nuvio_watched_item.delay") as delay:
            nuvio_outbound.enqueue_watched_delete(self.user, episode)
            delay.assert_called_once()
            _user_id, key = delay.call_args.args
            self.assertEqual(
                key,
                {"content_id": "tmdb:1396", "season": 1, "episode": 1},
            )

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
