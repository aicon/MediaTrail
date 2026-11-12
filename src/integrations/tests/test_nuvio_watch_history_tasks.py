from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from integrations.models import NuvioAccount
from integrations.tasks import (
    sync_nuvio_watch_history,
    sync_nuvio_watch_history_for_user,
)


class NuvioWatchHistoryTaskTests(TestCase):
    """Background delta poll locking and scheduling guards."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            "nuvio-sync-user",
            password="secret",
        )
        self.user.nuvio_sync_mark_played_enabled = True
        self.user.save(update_fields=["nuvio_sync_mark_played_enabled"])
        self.account = NuvioAccount.objects.create(
            user=self.user,
            email="encrypted-email",
            password="encrypted-password",
            profile_id=1,
            bootstrapped=True,
            cursor=10,
        )

    def test_delta_poll_skips_when_lock_held(self):
        cache.add(f"nuvio-watch-sync:{self.user.id}", "1", timeout=120)
        with patch("integrations.tasks.nuvio.NuvioImporter") as importer_cls:
            sync_nuvio_watch_history()
        importer_cls.assert_not_called()

    def test_delta_poll_runs_under_lock(self):
        with patch("integrations.tasks.nuvio.NuvioImporter") as importer_cls:
            importer_cls.return_value.sync_delta.return_value = ({}, "")
            sync_nuvio_watch_history()
        importer_cls.assert_called_once()
        importer_cls.return_value.sync_delta.assert_called_once_with()
        self.assertIsNone(cache.get(f"nuvio-watch-sync:{self.user.id}"))

    def test_one_shot_skips_when_lock_held(self):
        cache.add(f"nuvio-watch-sync:{self.user.id}", "1", timeout=120)
        with patch("integrations.tasks.nuvio.NuvioImporter") as importer_cls:
            sync_nuvio_watch_history_for_user(self.user.id)
        importer_cls.assert_not_called()
