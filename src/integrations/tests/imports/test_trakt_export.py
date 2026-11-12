"""Trakt website export ZIP validation and import wiring."""

import json
import zipfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from integrations.imports import trakt
from integrations.imports.helpers import MediaImportError


def _build_export_zip(**members):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(
                name if name.endswith(".json") else f"{name}.json",
                json.dumps(payload),
            )
    return buffer.getvalue()


class TraktExportInspectTests(TestCase):
    """Fail closed before Celery sees a bad archive."""

    def test_rejects_non_zip(self):
        with self.assertRaises(MediaImportError):
            trakt.inspect_trakt_export(BytesIO(b"not-a-zip"))

    def test_rejects_unrecognized_archive(self):
        payload = _build_export_zip(readme={"hello": "world"})
        with self.assertRaises(MediaImportError):
            trakt.inspect_trakt_export(BytesIO(payload))

    def test_rejects_empty_recognized_archive(self):
        payload = _build_export_zip(**{"user-profile": {"username": "dak"}})
        with self.assertRaises(MediaImportError):
            trakt.inspect_trakt_export(BytesIO(payload))

    def test_preview_counts_history_and_ratings(self):
        payload = _build_export_zip(
            **{
                "user-profile": {"username": "dak"},
                "watched-history": [
                    {
                        "type": "movie",
                        "movie": {"ids": {"tmdb": 550}},
                        "watched_at": "2024-01-01T00:00:00.000Z",
                    },
                ],
                "ratings-movies": [
                    {
                        "movie": {"ids": {"tmdb": 550}},
                        "rating": 8,
                        "rated_at": "2024-01-02T00:00:00.000Z",
                    },
                ],
                "lists-watchlist": [],
                "comments-movies": [],
            },
        )
        preview = trakt.inspect_trakt_export(BytesIO(payload))
        self.assertEqual(preview["username"], "dak")
        self.assertEqual(preview["counts"]["history"], 1)
        self.assertEqual(preview["counts"]["ratings"], 1)
        self.assertEqual(preview["counts"]["watchlist"], 0)


class TraktExportViewTests(TestCase):
    """Upload view validates before queueing."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("trakt-zip", password="secret")
        self.client.force_login(self.user)

    def test_bad_zip_is_rejected_without_queue(self):
        with patch("integrations.tasks.import_trakt.delay") as queued:
            response = self.client.post(
                reverse("import_trakt_export"),
                {
                    "mode": "new",
                    "trakt_export_zip": SimpleUploadedFile(
                        "bad.zip",
                        b"not-a-zip",
                        content_type="application/zip",
                    ),
                },
            )
        self.assertEqual(response.status_code, 302)
        queued.assert_not_called()

    def test_valid_zip_is_queued_after_preview(self):
        payload = _build_export_zip(
            **{
                "user-profile": {"username": "dak"},
                "watched-history": [
                    {
                        "type": "movie",
                        "movie": {"ids": {"tmdb": 550}},
                        "watched_at": "2024-01-01T00:00:00.000Z",
                    },
                ],
            },
        )
        with patch("integrations.tasks.import_trakt.delay") as queued:
            response = self.client.post(
                reverse("import_trakt_export"),
                {
                    "mode": "new",
                    "trakt_export_zip": SimpleUploadedFile(
                        "trakt.zip",
                        payload,
                        content_type="application/zip",
                    ),
                },
            )
        self.assertEqual(response.status_code, 302)
        queued.assert_called_once()
        self.assertEqual(queued.call_args.kwargs["mode"], "new")
        self.assertIsNotNone(queued.call_args.kwargs["file"])
