from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from app.detail_links import (
    apply_user_detail_links,
    build_external_links,
    resolve_port_hu_url,
    resolve_simkl_url,
    resolve_trakt_url,
    visible_detail_links,
)
from app.models import MediaTypes


class BuildExternalLinksTests(SimpleTestCase):
    def test_movie_links_are_static_only(self):
        links = build_external_links(
            {
                "imdb_id": "tt0179955",
                "wikidata_id": "Q713543",
            },
            media_type=MediaTypes.MOVIE.value,
            tmdb_id=123,
        )
        self.assertEqual(
            links["imdb"],
            "https://www.imdb.com/title/tt0179955/",
        )
        self.assertEqual(
            links["wikidata"],
            "https://www.wikidata.org/wiki/Q713543",
        )
        self.assertEqual(
            links["letterboxd"],
            "https://www.letterboxd.com/tmdb/123",
        )
        # Trakt/Simkl/Port.hu require resolution — not built from IMDb path.
        self.assertNotIn("trakt", links)
        self.assertNotIn("simkl", links)
        self.assertNotIn("port_hu", links)
        self.assertNotIn("tvdb", links)

    def test_tv_links_skip_letterboxd_without_imdb(self):
        links = build_external_links(
            {"tvdb_id": 330968, "wikidata_id": "Q1"},
            media_type=MediaTypes.TV.value,
        )
        self.assertNotIn("letterboxd", links)
        self.assertNotIn("trakt", links)
        self.assertNotIn("simkl", links)
        self.assertEqual(
            links["tvdb"],
            "https://www.thetvdb.com/dereferrer/series/330968",
        )


class PortHuResolutionTests(SimpleTestCase):
    @patch("app.detail_links.services.api_request")
    @patch("app.detail_links.cache")
    def test_macskafogo_p905_chain(self, mock_cache, mock_api):
        """Q713543 → P905 1546 → https://port.hu/jump/movie-1546"""
        mock_cache.get.return_value = None
        mock_api.return_value = {
            "claims": {
                "P905": [
                    {
                        "mainsnak": {
                            "snaktype": "value",
                            "datavalue": {"value": "1546", "type": "string"},
                        }
                    }
                ]
            }
        }
        url = resolve_port_hu_url("Q713543")
        self.assertEqual(url, "https://port.hu/jump/movie-1546")
        mock_api.assert_called_once()
        _, kwargs = mock_api.call_args
        self.assertIn("User-Agent", (kwargs.get("headers") or {}))
        mock_cache.set.assert_called()

    @patch("app.detail_links.services.api_request")
    @patch("app.detail_links.cache")
    def test_missing_p905_returns_none(self, mock_cache, mock_api):
        mock_cache.get.return_value = None
        mock_api.return_value = {"claims": {}}
        self.assertIsNone(resolve_port_hu_url("Q713543"))

    @patch("app.detail_links.services.api_request", side_effect=RuntimeError("403"))
    @patch("app.detail_links.cache")
    def test_api_error_does_not_cache_miss(self, mock_cache, _mock_api):
        mock_cache.get.return_value = None
        self.assertIsNone(resolve_port_hu_url("Q713543"))
        mock_cache.set.assert_not_called()

    def test_invalid_qid_skips_lookup(self):
        self.assertIsNone(resolve_port_hu_url("not-a-qid"))
        self.assertIsNone(resolve_port_hu_url(""))


class TraktResolutionTests(SimpleTestCase):
    @patch("app.detail_links.services.api_request")
    @patch("app.detail_links.cache")
    def test_macskafogo_wikidata_p8013(self, mock_cache, mock_api):
        mock_cache.get.return_value = None
        mock_api.return_value = {
            "claims": {
                "P8013": [
                    {
                        "mainsnak": {
                            "snaktype": "value",
                            "datavalue": {
                                "value": "movies/cat-city-1986",
                                "type": "string",
                            },
                        }
                    }
                ]
            }
        }
        url = resolve_trakt_url(
            wikidata_id="Q713543",
            imdb_id="tt0179955",
            media_type=MediaTypes.MOVIE.value,
        )
        self.assertEqual(url, "https://trakt.tv/movies/cat-city-1986")


class SimklResolutionTests(SimpleTestCase):
    @patch("app.detail_links.services.api_request")
    @patch("app.detail_links.cache")
    def test_macskafogo_simkl_id_lookup(self, mock_cache, mock_api):
        mock_cache.get.return_value = None
        mock_api.return_value = [
            {
                "type": "movie",
                "title": "Cat City",
                "ids": {"simkl": 137096, "slug": "cat-city"},
            }
        ]
        url = resolve_simkl_url(
            "tt0179955",
            media_type=MediaTypes.MOVIE.value,
        )
        self.assertEqual(url, "https://simkl.com/movies/137096/cat-city")
        mock_api.assert_called_once()
        args, kwargs = mock_api.call_args
        self.assertEqual(args[2], "https://api.simkl.com/search/id")
        self.assertEqual(kwargs["params"]["imdb"], "tt0179955")

    @patch("app.detail_links.services.api_request", side_effect=RuntimeError("down"))
    @patch("app.detail_links.cache")
    def test_simkl_error_does_not_cache_miss(self, mock_cache, _mock_api):
        mock_cache.get.return_value = None
        self.assertIsNone(resolve_simkl_url("tt0179955"))
        mock_cache.set.assert_not_called()

    def test_invalid_imdb_skips_lookup(self):
        self.assertIsNone(resolve_simkl_url("not-an-id"))
        self.assertIsNone(resolve_simkl_url(""))


class VisibleLinksTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="linkuser",
            password="pass12345",
        )

    @patch("app.detail_links.resolve_trakt_url", return_value="https://trakt.tv/movies/cat-city-1986")
    def test_defaults_show_imdb_wikidata_trakt(self, _mock_trakt):
        raw = build_external_links(
            {
                "imdb_id": "tt0179955",
                "wikidata_id": "Q713543",
                "tvdb_id": 1,
            },
            media_type=MediaTypes.MOVIE.value,
            tmdb_id=9,
        )
        visible = visible_detail_links(
            self.user,
            raw,
            wikidata_id="Q713543",
            imdb_id="tt0179955",
            media_type=MediaTypes.MOVIE.value,
        )
        self.assertEqual(
            list(visible.keys()),
            ["IMDb", "Wikidata", "Trakt"],
        )
        self.assertEqual(
            visible["Trakt"],
            "https://trakt.tv/movies/cat-city-1986",
        )

    @patch(
        "app.detail_links.resolve_port_hu_url",
        return_value="https://port.hu/jump/movie-1546",
    )
    def test_port_hu_only_when_enabled_and_resolved(self, _mock_port):
        self.user.link_port_hu_enabled = True
        self.user.link_imdb_enabled = False
        self.user.link_wikidata_enabled = False
        self.user.link_trakt_enabled = False
        self.user.save()
        visible = visible_detail_links(self.user, {}, wikidata_id="Q713543")
        self.assertEqual(
            visible,
            {"Port.hu": "https://port.hu/jump/movie-1546"},
        )

    @patch(
        "app.detail_links.resolve_simkl_url",
        return_value="https://simkl.com/movies/137096/cat-city",
    )
    @patch(
        "app.detail_links.resolve_trakt_url",
        return_value="https://trakt.tv/movies/cat-city-1986",
    )
    @patch(
        "app.detail_links.resolve_port_hu_url",
        return_value="https://port.hu/jump/movie-1546",
    )
    def test_macskafogo_enabled_links(
        self,
        _mock_port,
        _mock_trakt,
        _mock_simkl,
    ):
        self.user.link_simkl_enabled = True
        self.user.link_port_hu_enabled = True
        self.user.save()
        media = {
            "media_id": 60800,
            "external_ids": {
                "imdb_id": "tt0179955",
                "wikidata_id": "Q713543",
            },
            "external_links": {},
        }
        apply_user_detail_links(media, self.user, MediaTypes.MOVIE.value)
        self.assertEqual(
            media["external_links"]["Port.hu"],
            "https://port.hu/jump/movie-1546",
        )
        self.assertEqual(
            media["external_links"]["Simkl"],
            "https://simkl.com/movies/137096/cat-city",
        )
        self.assertEqual(
            media["external_links"]["Trakt"],
            "https://trakt.tv/movies/cat-city-1986",
        )
        self.assertNotIn("tt0179955", media["external_links"]["Simkl"])
        self.assertNotIn("tt0179955", media["external_links"]["Trakt"])

    def test_apply_rebuilds_from_external_ids(self):
        media = {
            "media_id": 42,
            "external_ids": {
                "imdb_id": "tt0179955",
                "wikidata_id": "Q713543",
            },
            "external_links": {"IMDb": "stale"},
        }
        with patch(
            "app.detail_links.resolve_trakt_url",
            return_value="https://trakt.tv/movies/cat-city-1986",
        ):
            apply_user_detail_links(media, self.user, MediaTypes.MOVIE.value)
        self.assertEqual(
            media["external_links"]["IMDb"],
            "https://www.imdb.com/title/tt0179955/",
        )
        self.assertIn("Trakt", media["external_links"])
