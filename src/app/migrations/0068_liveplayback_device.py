# Multi-device Now Watching: one live row per (user, device_id).

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


LEGACY_DEVICE_ID = "legacy"
LEGACY_DEVICE_LABEL = "Ismeretlen eszköz"


def consolidate_to_legacy(apps, schema_editor):
    """Keep newest row per user as legacy; delete the rest (live only)."""
    LivePlayback = apps.get_model("app", "LivePlayback")
    user_ids = (
        LivePlayback.objects.order_by()
        .values_list("user_id", flat=True)
        .distinct()
    )
    for user_id in user_ids:
        rows = list(
            LivePlayback.objects.filter(user_id=user_id).order_by("-updated_at", "-id"),
        )
        if not rows:
            continue
        keep = rows[0]
        keep.device_id = LEGACY_DEVICE_ID
        keep.device_label = LEGACY_DEVICE_LABEL
        keep.save(update_fields=["device_id", "device_label"])
        drop_ids = [row.id for row in rows[1:]]
        if drop_ids:
            LivePlayback.objects.filter(id__in=drop_ids).delete()


def noop_reverse(apps, schema_editor):
    """Cannot restore deleted live rows."""


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0067_remove_liveplayback_pending_player_command"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="liveplayback",
            name="device_id",
            field=models.CharField(default=LEGACY_DEVICE_ID, max_length=128),
        ),
        migrations.AddField(
            model_name="liveplayback",
            name="device_label",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.CreateModel(
            name="DeviceDisplayName",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("device_id", models.CharField(max_length=128)),
                ("custom_name", models.CharField(max_length=128)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="device_display_names",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "device_id"),
                        name="unique_device_display_name_per_user",
                    ),
                ],
            },
        ),
        migrations.RunPython(consolidate_to_legacy, noop_reverse),
        migrations.RemoveConstraint(
            model_name="liveplayback",
            name="unique_live_playback_per_user_item",
        ),
        migrations.AddConstraint(
            model_name="liveplayback",
            constraint=models.UniqueConstraint(
                fields=("user", "device_id"),
                name="unique_live_playback_per_user_device",
            ),
        ),
    ]
