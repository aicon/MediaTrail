"""Tests for Nuvio Library ↔ MediaTrail watchlist sync and catalog JSON."""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import Item, MediaTypes, Movie, Sources, Status, TV
from integrations import nuvio_library
from integrations.models import NuvioAccount
from lists.models import CustomList, CustomListItem
from integrations.imports import helpers as import_helpers


class NuvioLibrarySyncTests(TestCase):
    """Watchlist sync helpers and bootstrap skip rules."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("lib", password="secret")
        self.user.nuvio_sync_library_enabled = True
        self.user.save(update_fields=["nuvio_sync_library_enabled"])
        self.account = NuvioAccount.objects.create(
            user=self.user,
            email=import_helpers.encrypt("a@b.c"),
            password=import_helpers.encrypt("pw"),
            profile_id=1,
        )
        self.watchlist = CustomList.objects.create(
            name="Movie watchlist",
            owner=self.user,
        )
        self.account.watchlist_list = self.watchlist
        self.account.save(update_fields=["watchlist_list"])
        self.movie_item = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image="https://example.com/p.jpg",
        )
        self.tv_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image="https://example.com/bb.jpg",
        )

    def test_remove_from_watchlist_deletes_list_item_and_queues_nuvio(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        with patch("integrations.tasks.delete_nuvio_library_item.delay") as mock_delay:
            with patch(
                "integrations.nuvio_library.resolve_imdb_id_cached",
                return_value="tt0137523",
            ):
                nuvio_library.remove_from_nuvio_watchlist(self.user, self.movie_item)
        self.assertFalse(
            CustomListItem.objects.filter(
                custom_list=self.watchlist,
                item=self.movie_item,
            ).exists(),
        )
        mock_delay.assert_called_once()

    def test_movie_completed_removes_from_watchlist(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        with patch("integrations.tasks.delete_nuvio_library_item.delay"):
            with patch(
                "integrations.nuvio_library.resolve_imdb_id_cached",
                return_value="tt0137523",
            ):
                Movie.objects.create(
                    user=self.user,
                    item=self.movie_item,
                    status=Status.COMPLETED.value,
                )
        self.assertFalse(
            CustomListItem.objects.filter(
                custom_list=self.watchlist,
                item=self.movie_item,
            ).exists(),
        )

    def test_season_in_progress_removes_show_from_watchlist(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.tv_item)
        tv = TV.objects.create(
            user=self.user,
            item=self.tv_item,
            status=Status.PLANNING.value,
        )
        season_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="S1",
            image="",
            season_number=1,
        )
        from app.models import Season

        with patch("integrations.tasks.delete_nuvio_library_item.delay"):
            with patch(
                "integrations.nuvio_library.resolve_imdb_id_cached",
                return_value="tt0903747",
            ):
                Season.objects.create(
                    user=self.user,
                    item=season_item,
                    related_tv=tv,
                    status=Status.IN_PROGRESS.value,
                )
        self.assertFalse(
            CustomListItem.objects.filter(
                custom_list=self.watchlist,
                item=self.tv_item,
            ).exists(),
        )

    def test_bootstrap_skips_completed_movie_and_deletes_remote(self):
        with patch("integrations.tasks.delete_nuvio_library_item.delay"):
            Movie.objects.create(
                user=self.user,
                item=self.movie_item,
                status=Status.COMPLETED.value,
            )
        client = MagicMock()
        client.library_cursor.return_value = 10
        client.iter_library.return_value = [
            {
                "content_id": "tt0137523",
                "content_type": "movie",
                "name": "Fight Club",
            },
        ]
        self.account.imdb_map = {"tt0137523": "550"}
        self.account.save(update_fields=["imdb_map"])
        with patch("integrations.tasks.delete_nuvio_library_item.delay"):
            nuvio_library._bootstrap(self.user, client, self.watchlist, self.account)
        self.assertFalse(
            CustomListItem.objects.filter(
                custom_list=self.watchlist,
                item=self.movie_item,
            ).exists(),
        )
        client.delete_library_items.assert_called()
        self.account.refresh_from_db()
        self.assertTrue(self.account.library_bootstrapped)
        self.assertEqual(self.account.library_cursor, 10)

    def test_catalog_metas_use_imdb_map_cache(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        self.account.imdb_map = {"tt0137523": "550"}
        self.account.save(update_fields=["imdb_map"])
        with patch("app.providers.services.get_media_metadata") as mock_meta:
            metas = nuvio_library.catalog_metas(
                self.user,
                f"mt-list-{self.watchlist.id}-movie",
                "movie",
            )
        mock_meta.assert_not_called()
        self.assertEqual(metas[0]["id"], "tt0137523")
        self.assertEqual(metas[0]["type"], "movie")

    def test_catalog_name_adds_type_suffix_when_mixed(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.tv_item)
        catalogs = nuvio_library.catalog_manifest_entries(self.user)
        names = {c["id"]: c["name"] for c in catalogs}
        self.assertIn("— Movies", names[f"mt-list-{self.watchlist.id}-movie"])
        self.assertIn("— Series", names[f"mt-list-{self.watchlist.id}-series"])

    @override_settings(URLS=["https://mediatrail.example"])
    def test_manifest_includes_list_catalogs(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        response = self.client.get(
            reverse("nuvio_manifest", kwargs={"token": self.user.token}),
        )
        body = response.json()
        self.assertIn("catalog", body["resources"])
        catalog_ids = {c["id"] for c in body["catalogs"]}
        self.assertIn(f"mt-list-{self.watchlist.id}-movie", catalog_ids)
        self.assertIn(f"mt-list-{self.watchlist.id}-series", catalog_ids)

    def test_catalog_endpoint_returns_metas(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        self.account.imdb_map = {"tt0137523": "550"}
        self.account.save(update_fields=["imdb_map"])
        response = self.client.get(
            reverse(
                "nuvio_catalog",
                kwargs={
                    "token": self.user.token,
                    "media_type": "movie",
                    "catalog_id": f"mt-list-{self.watchlist.id}-movie",
                },
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["metas"][0]["id"], "tt0137523")

    def test_outbound_push_uses_single_canonical_imdb_id(self):
        """Never push tt + imdb:tt + tmdb: for the same title."""
        with patch(
            "integrations.nuvio_library.resolve_imdb_id_cached",
            return_value="tt0137523",
        ):
            payloads = nuvio_library._library_payloads_for_item(
                self.user,
                self.movie_item,
            )
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["content_id"], "tt0137523")
        self.assertEqual(payloads[0]["content_type"], "movie")

    def test_delete_keys_cover_all_id_variants(self):
        with patch(
            "integrations.nuvio_library.resolve_imdb_id_cached",
            return_value="tt0137523",
        ):
            keys = nuvio_library._library_keys_for_item(self.user, self.movie_item)
        content_ids = {k["content_id"] for k in keys}
        self.assertEqual(
            content_ids,
            {"tt0137523", "imdb:tt0137523", "tmdb:550"},
        )

    def test_remove_queues_all_id_variants(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        with patch("integrations.tasks.delete_nuvio_library_item.delay") as mock_delay:
            with patch(
                "integrations.nuvio_library.resolve_imdb_id_cached",
                return_value="tt0137523",
            ):
                nuvio_library.remove_from_nuvio_watchlist(self.user, self.movie_item)
        keys = mock_delay.call_args.args[1]
        content_ids = {k["content_id"] for k in keys}
        self.assertEqual(
            content_ids,
            {"tt0137523", "imdb:tt0137523", "tmdb:550"},
        )

    def test_bootstrap_does_not_push_when_any_id_variant_exists(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        client = MagicMock()
        client.library_cursor.return_value = 3
        client.iter_library.return_value = [
            {
                "content_id": "imdb:tt0137523",
                "content_type": "movie",
                "name": "Fight Club",
            },
        ]
        self.account.imdb_map = {"tt0137523": "550"}
        self.account.save(update_fields=["imdb_map"])
        with patch(
            "integrations.nuvio_library.resolve_imdb_id_cached",
            return_value="tt0137523",
        ):
            nuvio_library._bootstrap(self.user, client, self.watchlist, self.account)
        client.push_library_items.assert_not_called()

    def test_bootstrap_dedupes_remote_id_variants(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        client = MagicMock()
        client.library_cursor.return_value = 5
        client.iter_library.return_value = [
            {
                "content_id": "tt0137523",
                "content_type": "movie",
                "name": "Fight Club",
            },
            {
                "content_id": "imdb:tt0137523",
                "content_type": "movie",
                "name": "Fight Club",
            },
            {
                "content_id": "tmdb:550",
                "content_type": "movie",
                "name": "Fight Club",
            },
        ]
        self.account.imdb_map = {"tt0137523": "550"}
        self.account.save(update_fields=["imdb_map"])
        with patch(
            "integrations.nuvio_library.resolve_imdb_id_cached",
            return_value="tt0137523",
        ):
            nuvio_library._bootstrap(self.user, client, self.watchlist, self.account)
        client.push_library_items.assert_not_called()
        client.delete_library_items.assert_called()
        deleted_ids = {
            k["content_id"] for k in client.delete_library_items.call_args.args[0]
        }
        self.assertIn("imdb:tt0137523", deleted_ids)
        self.assertIn("tmdb:550", deleted_ids)
        self.assertNotIn("tt0137523", deleted_ids)
