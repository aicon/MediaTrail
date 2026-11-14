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
            title="San Francisco utcáin",
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

    def test_remove_also_clears_season_row_on_watchlist(self):
        """Sticky 'Show S1' CustomListItem must leave with the parent TV."""
        season_item = Item.objects.create(
            media_id="2468",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="San Francisco utcáin",
            image="",
            season_number=1,
        )
        tv_item = Item.objects.create(
            media_id="2468",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="San Francisco utcáin",
            image="",
        )
        CustomListItem.objects.create(custom_list=self.watchlist, item=season_item)
        with patch("integrations.tasks.delete_nuvio_library_item.delay") as mock_delay:
            with patch(
                "integrations.nuvio_library.resolve_imdb_id_cached",
                return_value="tt0068135",
            ):
                nuvio_library.remove_from_nuvio_watchlist(
                    self.user,
                    tmdb_id="2468",
                    media_type=MediaTypes.TV.value,
                )
        self.assertFalse(
            CustomListItem.objects.filter(
                custom_list=self.watchlist,
                item=season_item,
            ).exists(),
        )
        self.assertFalse(
            CustomListItem.objects.filter(
                custom_list=self.watchlist,
                item=tv_item,
            ).exists(),
        )
        mock_delay.assert_called_once()
        deleted_ids = {k["content_id"] for k in mock_delay.call_args.args[1]}
        self.assertEqual(
            deleted_ids,
            {"tt0068135", "imdb:tt0068135", "tmdb:2468"},
        )

    def test_normalize_watchlist_item_maps_season_to_tv(self):
        season_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Breaking Bad",
            image="",
            season_number=1,
        )
        TV.objects.create(
            user=self.user,
            item=self.tv_item,
            status=Status.PLANNING.value,
        )
        parent = nuvio_library.normalize_watchlist_item(self.user, season_item)
        self.assertEqual(parent, self.tv_item)

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
        with (
            patch("app.providers.services.get_media_metadata") as mock_meta,
            patch("integrations.nuvio_library._catalog_display_meta", return_value={}),
        ):
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
        with patch("integrations.nuvio_library._catalog_display_meta", return_value={}):
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

    def test_catalog_metas_include_hero_fields(self):
        CustomListItem.objects.create(custom_list=self.watchlist, item=self.movie_item)
        self.account.imdb_map = {"tt0137523": "550"}
        self.account.save(update_fields=["imdb_map"])
        display = {
            "name": "Fight Club",
            "poster": "https://image.tmdb.org/t/p/w500/poster.jpg",
            "background": "https://image.tmdb.org/t/p/w1280/back.jpg",
            "logo": "https://image.tmdb.org/t/p/w500/logo.png",
            "description": "An insomniac office worker.",
            "releaseInfo": "1999",
            "released": "1999-10-15",
            "genres": ["Drama"],
            "runtime": "139 min",
            "trailerYtId": "abc123",
        }
        with patch(
            "integrations.nuvio_library._catalog_display_meta",
            return_value=display,
        ):
            metas = nuvio_library.catalog_metas(
                self.user,
                f"mt-list-{self.watchlist.id}-movie",
                "movie",
            )
        meta = metas[0]
        self.assertEqual(meta["description"], "An insomniac office worker.")
        self.assertEqual(meta["releaseInfo"], "1999")
        self.assertEqual(meta["background"], display["background"])
        self.assertEqual(meta["logo"], display["logo"])
        self.assertEqual(meta["genres"], ["Drama"])
        self.assertEqual(meta["trailers"], [{"source": "abc123", "type": "Trailer"}])
        self.assertEqual(meta["trailerStreams"], [{"ytId": "abc123"}])

    def test_display_from_tmdb_prefers_language_logo_and_year_span(self):
        display = nuvio_library._display_from_tmdb(
            {
                "name": "The Streets of San Francisco",
                "overview": "A veteran detective.",
                "first_air_date": "1972-09-16",
                "last_air_date": "1977-06-09",
                "backdrop_path": "/back.jpg",
                "poster_path": "/poster.jpg",
                "genres": [{"name": "Drama"}, {}],
                "episode_run_time": [49],
                "images": {
                    "logos": [
                        {"iso_639_1": "en", "file_path": "/en.png", "vote_average": 9},
                        {"iso_639_1": "hu", "file_path": "/hu.png", "vote_average": 1},
                    ],
                },
                "videos": {
                    "results": [
                        {
                            "site": "YouTube",
                            "type": "Teaser",
                            "key": "teaser",
                            "iso_639_1": "hu",
                            "official": True,
                        },
                        {
                            "site": "YouTube",
                            "type": "Trailer",
                            "key": "en-trailer",
                            "iso_639_1": "en",
                            "official": True,
                            "size": 1080,
                        },
                        {
                            "site": "YouTube",
                            "type": "Trailer",
                            "key": "hu-trailer",
                            "iso_639_1": "hu",
                            "official": True,
                            "size": 720,
                        },
                    ],
                },
            },
            "hu",
        )
        self.assertEqual(display["releaseInfo"], "1972-1977")
        self.assertEqual(display["trailerYtId"], "hu-trailer")
        self.assertEqual(display["released"], "1972-09-16")
        self.assertEqual(display["logo"], "https://image.tmdb.org/t/p/w500/hu.png")
        self.assertEqual(display["runtime"], "49 min")
        self.assertEqual(display["genres"], ["Drama"])
        self.assertIn("/w1280/back.jpg", display["background"])

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
