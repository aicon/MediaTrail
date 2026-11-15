from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from app.models import Item, LivePlayback, LivePlaybackStatus, MediaTypes, Sources
from integrations.emby_live import (
    DISCOVERY_POLLS,
    EmbyPollError,
    fetch_sessions,
    handle_live_event,
    playing_sessions,
    provider_ids,
    run_poll,
    save_connection,
    ticks_to_ms,
)
from integrations.webhooks.emby import EmbyWebhookProcessor

EMBY_USER = "8b4e6371c425401f92b20af74684971e"
DEVICE = "d58cccd8d9aa6afc"
POSITION = 6_703_400_000
RUNTIME = 53_808_000_000


def _item():
    return {
        "Name": "Sherlock Holmes meggyilkolása",
        "Type": "Episode",
        "SeriesName": "Gyilkos sorok",
        "IndexNumber": 1,
        "ParentIndexNumber": 1,
        "RunTimeTicks": RUNTIME,
        "ProviderIds": {"Tvdb": "330968", "IMDB": "tt0087757"},
    }


def _session(*, paused=False, user_id=EMBY_USER, device_id=DEVICE, playing=True):
    row = {
        "UserId": user_id,
        "DeviceId": device_id,
        "DeviceName": "Xiaomi Pad 7 Pro",
        "PlayState": {
            "PositionTicks": POSITION,
            "IsPaused": paused,
        },
    }
    if playing:
        row["NowPlayingItem"] = _item()
    return row


def _event(name, *, device_id=DEVICE):
    payload = {
        "Event": name,
        "User": {"Name": "viewer", "Id": EMBY_USER},
        "Item": _item(),
        "PlaybackInfo": {
            "PositionTicks": POSITION,
            "PlayedToCompletion": False,
        },
    }
    if device_id is not None:
        payload["Session"] = {
            "DeviceId": device_id,
            "DeviceName": "Xiaomi Pad 7 Pro",
            "Id": "session-id",
        }
    return payload


class EmbyLiveTests(TestCase):
    """Emby session polling and playback webhooks."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="emby-user")
        save_connection(
            self.user,
            "http://emby.local:8096",
            "secret-key",
            EMBY_USER,
            "viewer",
        )
        self.episode = Item.objects.create(
            media_id="484",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Gyilkos sorok",
            image="https://example.com/ep.jpg",
            season_number=1,
            episode_number=1,
        )
        self.metadata = patch(
            "app.playback_operations._fetch_display_metadata",
            return_value={},
        )
        self.metadata.start()
        self.resolve = patch(
            "integrations.emby_live.resolve_now_playing",
            return_value=(MediaTypes.TV.value, "484", 1, 1),
        )
        self.resolve.start()
        self.schedule = patch("integrations.emby_live.request_poll")
        self.schedule.start()

    def tearDown(self):
        self.schedule.stop()
        self.resolve.stop()
        self.metadata.stop()
        cache.clear()

    def test_ticks_and_provider_case(self):
        self.assertEqual(ticks_to_ms(POSITION), 670_340)
        self.assertEqual(ticks_to_ms(RUNTIME), 5_380_800)
        self.assertEqual(
            provider_ids(_item()),
            {"tmdb_id": None, "imdb_id": "tt0087757", "tvdb_id": "330968"},
        )
        ids = EmbyWebhookProcessor()._extract_external_ids({"Item": _item()})
        self.assertEqual(ids["imdb_id"], "tt0087757")
        self.assertEqual(ids["tvdb_id"], "330968")

    def test_idle_sessions_are_ignored(self):
        rows = [
            _session(playing=False, device_id="browser"),
            _session(user_id="someone-else", device_id="other-pad"),
            _session(),
        ]
        playing = playing_sessions(rows, EMBY_USER)
        self.assertEqual([row["DeviceId"] for row in playing], [DEVICE])

    def test_start_writes_strip_and_percent(self):
        handle_live_event(self.user, _event("playback.start"))
        row = LivePlayback.objects.get(user=self.user)
        self.assertEqual(row.device_id, f"emby:{DEVICE}")
        self.assertEqual(row.percent_watched, 12)
        self.assertEqual(row.status, LivePlaybackStatus.WATCHING)
        self.assertEqual(row.device_label, "Xiaomi Pad 7 Pro")

    def test_stop_removes_only_that_device(self):
        handle_live_event(self.user, _event("playback.start"))
        handle_live_event(self.user, _event("playback.start", device_id="other"))
        LivePlayback.objects.create(
            user=self.user,
            item=self.episode,
            device_id="nuvio-phone",
            position_ms=1,
            duration_ms=10,
        )
        handle_live_event(self.user, _event("playback.stop"))
        remaining = set(
            LivePlayback.objects.filter(user=self.user).values_list(
                "device_id",
                flat=True,
            ),
        )
        self.assertEqual(remaining, {f"emby:other", "nuvio-phone"})

    def test_pause_does_not_start_tracking(self):
        handle_live_event(self.user, _event("playback.pause"))
        self.assertFalse(LivePlayback.objects.filter(user=self.user).exists())

    def test_unpause_after_stop_waits_for_sessions(self):
        handle_live_event(self.user, _event("playback.start"))
        handle_live_event(self.user, _event("playback.stop"))
        handle_live_event(self.user, _event("playback.unpause"))
        self.assertFalse(LivePlayback.objects.filter(user=self.user).exists())

        with patch(
            "integrations.emby_live.fetch_sessions",
            return_value=[_session()],
        ):
            run_poll(self.user.id)
        row = LivePlayback.objects.get(user=self.user)
        self.assertEqual(row.device_id, f"emby:{DEVICE}")
        self.assertEqual(row.status, LivePlaybackStatus.WATCHING)

    def test_two_misses_remove_strip_and_error_keeps_it(self):
        handle_live_event(self.user, _event("playback.start"))
        LivePlayback.objects.create(
            user=self.user,
            item=self.episode,
            device_id="nuvio-phone",
            position_ms=1,
            duration_ms=10,
        )
        with patch("integrations.emby_live.fetch_sessions", side_effect=RuntimeError):
            run_poll(self.user.id)
        self.assertTrue(
            LivePlayback.objects.filter(device_id=f"emby:{DEVICE}").exists(),
        )

        with patch("integrations.emby_live.fetch_sessions", return_value=[]):
            run_poll(self.user.id)
            self.assertTrue(
                LivePlayback.objects.filter(device_id=f"emby:{DEVICE}").exists(),
            )
            run_poll(self.user.id)
        self.assertFalse(
            LivePlayback.objects.filter(device_id=f"emby:{DEVICE}").exists(),
        )
        self.assertTrue(
            LivePlayback.objects.filter(device_id="nuvio-phone").exists(),
        )

    def test_failed_request_is_not_an_empty_session_list(self):
        with patch(
            "integrations.emby_live.requests.get",
            side_effect=requests.ConnectionError("down"),
        ):
            with self.assertRaises(EmbyPollError):
                fetch_sessions("http://emby.local:8096", "secret-key")

    def test_discovery_survives_the_first_empty_poll(self):
        handle_live_event(self.user, _event("playback.start", device_id=None))
        with patch("integrations.emby_live.fetch_sessions", return_value=[]):
            run_poll(self.user.id)
        state = cache.get(f"emby-live:{self.user.id}")
        self.assertEqual(state["discovery"], DISCOVERY_POLLS - 1)
        self.assertFalse(LivePlayback.objects.filter(user=self.user).exists())

    def test_second_start_is_kept_while_a_poll_holds_the_lock(self):
        self.schedule.stop()
        cache.add(f"emby-live-lock:{self.user.id}", "1", timeout=30)
        try:
            with patch("integrations.tasks.poll_emby_sessions.apply_async"):
                handle_live_event(self.user, _event("playback.start", device_id="pad-b"))
                run_poll(self.user.id)
        finally:
            self.schedule.start()
        state = cache.get(f"emby-live:{self.user.id}")
        self.assertIn("pad-b", state["devices"])
        self.assertEqual(cache.get(f"emby-live-want:{self.user.id}"), "1")
