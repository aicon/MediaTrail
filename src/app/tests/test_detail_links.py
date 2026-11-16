from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from app.detail_links import (
    apply_user_detail_links,
    build_external_links,
    resolve_port_hu_url,
    visible_detail_links,
)
from app.models import MediaTypes


class BuildExternalLinksTests(SimpleTestCase):
    def test_movie_links_use_imdb_and_tmdb_where_documented(self):
        links = build_external_links(
            {
                "imdb_id": "tt0085192",
                "wikidata_id": "Q713543",
            },
            media_type=MediaTypes.MOVIE.value,
            tmdb_id=123,
        )
        self.assertEqual(
            links["imdb"],
            "https://www.imdb.com/title/tt0085192/",
        )
        self.assertEqual(
            links["wikidata"],
            "https://www.wikidata.org/wiki/Q713543",
        )
        self.assertEqual(
            links["letterboxd"],
            "https://www.letterboxd.com/tmdb/123",
        )
        self.assertEqual(links["trakt"], "https://trakt.tv/movies/tt0085192")
        self.assertEqual(links["simkl"], "https://simkl.com/movies/tt0085192")
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
    def test_port_hu_uses_wikidata_p905(self, mock_cache, mock_api):
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
        mock_cache.set.assert_called()

    @patch("app.detail_links.services.api_request")
    @patch("app.detail_links.cache")
    def test_missing_p905_returns_none(self, mock_cache, mock_api):
        mock_cache.get.return_value = None
        mock_api.return_value = {"claims": {}}
        self.assertIsNone(resolve_port_hu_url("Q713543"))

    def test_invalid_qid_skips_lookup(self):
        self.assertIsNone(resolve_port_hu_url("not-a-qid"))
        self.assertIsNone(resolve_port_hu_url(""))


class VisibleLinksTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="linkuser",
            password="pass12345",
        )

    def test_defaults_show_imdb_wikidata_trakt(self):
        raw = build_external_links(
            {
                "imdb_id": "tt0085192",
                "wikidata_id": "Q713543",
                "tvdb_id": 1,
            },
            media_type=MediaTypes.MOVIE.value,
            tmdb_id=9,
        )
        visible = visible_detail_links(self.user, raw, wikidata_id="Q713543")
        self.assertEqual(
            list(visible.keys()),
            ["IMDb", "Wikidata", "Trakt"],
        )

    @patch("app.detail_links.resolve_port_hu_url", return_value="https://port.hu/jump/movie-1546")
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

    def test_apply_rebuilds_from_external_ids(self):
        media = {
            "media_id": 42,
            "external_ids": {
                "imdb_id": "tt0085192",
                "wikidata_id": "Q713543",
            },
            "external_links": {"IMDb": "stale"},
        }
        apply_user_detail_links(media, self.user, MediaTypes.MOVIE.value)
        self.assertEqual(
            media["external_links"]["IMDb"],
            "https://www.imdb.com/title/tt0085192/",
        )
        self.assertIn("Trakt", media["external_links"])
