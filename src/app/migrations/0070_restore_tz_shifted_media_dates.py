"""Repair start_date/end_date values shifted by the original migration 0062.

Backup before applying in production: this migration rewrites stored datetimes.

See app.date_repair for the row-matching rules (history must still equal the
replayed buggy TruncMinute write; CET/CEST offsets differ on Europe/Budapest).

Port of FuzzyGrim/Yamtrack 0064_restore_tz_shifted_media_dates (v0.26.1).
Renumbered because MediaTrail already used 0064 for liveplayback.
"""

from django.db import migrations

from app.date_repair import restore_shifted_dates


class Migration(migrations.Migration):
    """Repair start_date/end_date values shifted by the original migration 0062."""

    dependencies = [
        ("app", "0069_liveplayback_stable_order"),
    ]

    operations = [
        migrations.RunPython(
            restore_shifted_dates,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
