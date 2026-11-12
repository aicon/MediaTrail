"""Repair helpers for dates shifted by the buggy TruncMinute in migration 0062.

Backup before applying the companion data migration in production: it rewrites
stored datetimes. Row scope: only rows whose newest simple-history values still
match the replayed buggy write are restored; later edits are left alone.

DST matters: Europe/Budapest is CET (+1) or CEST (+2) depending on the instant,
so the shift is not a fixed one-hour offset year-round.
"""

from __future__ import annotations

from datetime import UTC

from django.db.models import Q

BATCH_SIZE = 2000

START_AND_END_DATE_MODELS = [
    "Movie",
    "Anime",
    "Manga",
    "Game",
    "Book",
    "Comic",
    "BoardGame",
    "BasicMedia",
]
START_AND_END_DATE_FIELDS = ("start_date", "end_date")


def shifted_value(original, tz):
    """Replay what the buggy 0062 wrote for an original UTC value."""
    try:
        local = original.astimezone(tz)
    except (OverflowError, ValueError):
        # 0062 would have crashed on this row instead of shifting it.
        return None
    return local.replace(tzinfo=UTC, second=0, microsecond=0)


def latest_history(history_model, ids, fields):
    """Map each id to the field values of its newest historical record."""
    records = (
        history_model.objects.filter(id__in=ids)
        .order_by("id", "-history_date", "-history_id")
        .values_list("id", *fields)
        .iterator()
    )

    latest = {}
    for record in records:
        latest.setdefault(record[0], record[1:])
    return latest


def restore_model_dates(apps, model_name, fields, tz):
    """Undo the timezone shift on every row of a single model."""
    model = apps.get_model("app", model_name)
    history_model = apps.get_model("app", f"Historical{model_name}")

    tracked = Q()
    for field in fields:
        tracked |= Q(**{f"{field}__isnull": False})

    ids = list(
        model.objects.filter(tracked).order_by("pk").values_list("pk", flat=True),
    )

    for offset in range(0, len(ids), BATCH_SIZE):
        batch = ids[offset : offset + BATCH_SIZE]
        originals = latest_history(history_model, batch, fields)

        updates = []
        for media in model.objects.filter(pk__in=batch):
            original_values = originals.get(media.pk)
            if original_values is None:
                # No history to compare against, so the shift is undetectable.
                continue

            restored = False
            for field, original in zip(fields, original_values, strict=True):
                if original is None:
                    continue

                stored = getattr(media, field)
                expected = original.replace(second=0, microsecond=0)
                if stored == expected or stored != shifted_value(original, tz):
                    continue

                setattr(media, field, expected)
                restored = True

            if restored:
                updates.append(media)

        if updates:
            model.objects.bulk_update(updates, fields)


def restore_shifted_dates(apps, schema_editor, tz=None):
    """Pull every date 0062 shifted back onto its original instant."""
    from django.conf import settings

    if tz is None:
        tz = settings.TZ

    for model_name in START_AND_END_DATE_MODELS:
        restore_model_dates(apps, model_name, START_AND_END_DATE_FIELDS, tz)

    restore_model_dates(apps, "Episode", ("end_date",), tz)
