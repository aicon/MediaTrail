"""Tests for hybrid recommendation sources, cache, and merge."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.models import RecommendationSourceCache
from app.providers import recommendation_cache, recommendations
from app.providers.imdb_recommendations import parse_more_like_this_html
from app.recommendation_sources import (
    enabled_source_keys,
    parse_source_keys,
    user_source_enabled,
)
from users.models import User


IMDB_HTML = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"mainColumnData":{"moreLikeThisTitles":{"edges":[
  {"node":{"id":"tt1111111"}},
  {"node":{"id":"tt2222222"}},
  {"node":{"id":"tt1111111"}}
]}}}}}
</script>
</body></html>
"""


class RecommendationSourcesTests(TestCase):
    """Preference helpers for recommendation engines."""

    def setUp(self):
        self.user = User.objects.create_user(username="recuser", password="pass")

    def test_defaults_tmdb_and_imdb(self):
        self.assertEqual(enabled_source_keys(self.user), ["tmdb", "imdb"])
        self.assertFalse(user_source_enabled(self.user, "ai"))

    def test_ai_requires_key(self):
        self.user.rec_ai_enabled = True
        self.user.save(update_fields=["rec_ai_enabled"])
        self.assertFalse(user_source_enabled(self.user, "ai"))
        self.user.gemini_api_key = "encrypted-value"
        self.user.save(update_fields=["gemini_api_key"])
        self.assertTrue(user_source_enabled(self.user, "ai"))

    def test_parse_sources_filters_unknown(self):
        keys = parse_source_keys("tmdb,ai,nope", self.user)
        self.assertEqual(keys, ["tmdb"])


class ImdbParseTests(TestCase):
    """IMDb __NEXT_DATA__ parsing."""

    def test_parse_more_like_this(self):
        ids = parse_more_like_this_html(IMDB_HTML)
        self.assertEqual(ids, ["tt1111111", "tt2222222"])

    def test_parse_missing_blob(self):
        self.assertEqual(parse_more_like_this_html("<html></html>"), [])


class RecommendationCacheTests(TestCase):
    """Durable SQLite recommendation cache."""

    def test_roundtrip_and_expiry(self):
        recommendation_cache.set_cached_payload(
            "imdb",
            "movie",
            "tt0095016",
            ["tt1111111"],
        )
        self.assertEqual(
            recommendation_cache.get_cached_payload("imdb", "movie", "tt0095016"),
            ["tt1111111"],
        )
        RecommendationSourceCache.objects.filter(
            source="imdb",
            seed_key="tt0095016",
        ).update(expires_at=timezone.now() - timedelta(days=1))
        self.assertIsNone(
            recommendation_cache.get_cached_payload("imdb", "movie", "tt0095016")
        )


class RecommendationMergeTests(TestCase):
    """Dedupe and self-exclude in the hybrid pipeline."""

    def test_merge_dedupes_and_excludes_seed(self):
        buckets = {
            "tmdb": [
                {
                    "media_id": 1,
                    "media_type": "movie",
                    "title": "A",
                    "image": None,
                    "source": "tmdb",
                },
                {
                    "media_id": 99,
                    "media_type": "movie",
                    "title": "Seed",
                    "image": None,
                    "source": "tmdb",
                },
            ],
            "imdb": [
                {
                    "media_id": 1,
                    "media_type": "movie",
                    "title": "A",
                    "image": None,
                    "source": "tmdb",
                },
                {
                    "media_id": 2,
                    "media_type": "movie",
                    "title": "B",
                    "image": None,
                    "source": "tmdb",
                },
            ],
        }
        merged = recommendations._merge(
            buckets,
            exclude_media_id="99",
            exclude_type="movie",
        )
        self.assertEqual([item["media_id"] for item in merged], [1, 2])
        self.assertEqual(merged[0]["sources"], ["TMDB", "IMDb"])
        self.assertEqual(merged[1]["sources"], ["IMDb"])

    @patch("app.providers.recommendations._from_imdb", return_value=[])
    @patch("app.providers.recommendations._from_ai", return_value=[])
    def test_build_falls_back_when_extra_sources_empty(self, _ai, _imdb):
        user = User.objects.create_user(username="fallback", password="pass")
        metadata = {
            "media_id": 60800,
            "title": "Cat City",
            "related": {
                "recommendations": [
                    {
                        "media_id": 10,
                        "media_type": "movie",
                        "title": "Other",
                        "image": None,
                        "source": "tmdb",
                    }
                ]
            },
            "external_ids": {},
        }
        result = recommendations.build_recommendations(
            user,
            metadata,
            "movie",
            sources=["tmdb", "imdb"],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["media_id"], 10)
        self.assertEqual(result[0]["sources"], ["TMDB"])
