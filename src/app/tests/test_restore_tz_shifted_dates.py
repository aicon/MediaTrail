"""Tests for repairing dates shifted by the buggy TruncMinute in 0062."""

from datetime import UTC, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from app.date_repair import restore_model_dates, shifted_value
from app.models import Episode, Item, MediaTypes, Season, Sources, Status, TV


BUDAPEST = ZoneInfo("Europe/Budapest")


def _season_metadata():
    return {
        "title": "Starsky",
        "image": "http://example.test/s2.jpg",
        "season/2": {
            "episodes": [
                {"episode_number": n, "still_path": None, "air_date": "1977-01-01"}
                for n in range(1, 25)
            ],
        },
    }


class ShiftedValueTests(TestCase):
    """Replay the buggy 0062 write using the deployment timezone."""

    def test_cet_winter_offset_is_one_hour(self):
        # 2024-01-15 12:00 UTC -> 13:00 CET; buggy write stores 13:00 as UTC.
        original = datetime(2024, 1, 15, 12, 0, 30, tzinfo=UTC)
        expected = datetime(2024, 1, 15, 13, 0, tzinfo=UTC)
        self.assertEqual(shifted_value(original, BUDAPEST), expected)

    def test_cest_summer_offset_is_two_hours(self):
        # 2024-07-15 12:00 UTC -> 14:00 CEST; not a fixed +1h year-round.
        original = datetime(2024, 7, 15, 12, 0, 45, tzinfo=UTC)
        expected = datetime(2024, 7, 15, 14, 0, tzinfo=UTC)
        self.assertEqual(shifted_value(original, BUDAPEST), expected)

    def test_dst_spring_forward_uses_local_offset_for_that_instant(self):
        # After the 2024-03-31 spring forward, Budapest is CEST (+2).
        original = datetime(2024, 3, 31, 12, 0, 10, tzinfo=UTC)
        expected = datetime(2024, 3, 31, 14, 0, tzinfo=UTC)
        self.assertEqual(shifted_value(original, BUDAPEST), expected)


@override_settings(TZ=BUDAPEST)
class RestoreTzShiftedEpisodeDatesTests(TestCase):
    """Only rows whose stored value still matches the replayed shift are restored."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("tz-user", password="secret")
        self.tv_item = Item.objects.create(
            media_id="1532",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Starsky",
            image="http://example.test/tv.jpg",
        )
        self.season_item = Item.objects.create(
            media_id="1532",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Starsky",
            image="http://example.test/s2.jpg",
            season_number=2,
        )
        self.tv = TV.objects.create(
            item=self.tv_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        self.season = Season.objects.create(
            item=self.season_item,
            user=self.user,
            related_tv=self.tv,
            status=Status.IN_PROGRESS.value,
        )

    def _make_episode(self, episode_number, end_date):
        item = Item.objects.create(
            media_id="1532",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Starsky",
            image=f"http://example.test/e{episode_number}.jpg",
            season_number=2,
            episode_number=episode_number,
        )
        with patch(
            "app.providers.services.get_media_metadata",
            return_value=_season_metadata(),
        ):
            episode = Episode(
                item=item,
                related_season=self.season,
                end_date=end_date,
            )
            episode.save()
        return episode

    def test_restores_shifted_episode_and_leaves_edited_row_alone(self):
        winter_original = datetime(2024, 1, 15, 12, 0, 30, tzinfo=UTC)
        winter_shifted = shifted_value(winter_original, BUDAPEST)
        summer_original = datetime(2024, 7, 15, 12, 0, 45, tzinfo=UTC)
        summer_shifted = shifted_value(summer_original, BUDAPEST)
        edited_current = datetime(2024, 8, 1, 18, 30, tzinfo=UTC)

        # Save with the pre-0062 value so history keeps the original instant.
        shifted_episode = self._make_episode(21, winter_original)
        # Mimic buggy 0062: .update() shifts the row without writing history.
        Episode.objects.filter(pk=shifted_episode.pk).update(end_date=winter_shifted)

        summer_episode = self._make_episode(23, summer_original)
        Episode.objects.filter(pk=summer_episode.pk).update(end_date=summer_shifted)

        # User edited after the buggy migration: history matches the new value.
        edited_episode = self._make_episode(22, edited_current)

        restore_model_dates(apps, "Episode", ("end_date",), BUDAPEST)

        shifted_episode.refresh_from_db()
        summer_episode.refresh_from_db()
        edited_episode.refresh_from_db()

        self.assertEqual(
            shifted_episode.end_date,
            winter_original.replace(second=0, microsecond=0),
        )
        self.assertEqual(
            summer_episode.end_date,
            summer_original.replace(second=0, microsecond=0),
        )
        self.assertEqual(edited_episode.end_date, edited_current)
