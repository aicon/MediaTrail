from django.db import migrations


def create_schedule(apps, schema_editor):
    """Pull Nuvio watched-history deltas every few minutes when toggles are on."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _created = IntervalSchedule.objects.get_or_create(
        every=5,
        period="minutes",
    )
    PeriodicTask.objects.update_or_create(
        name="sync_nuvio_watch_history",
        defaults={
            "task": "Sync Nuvio watch history",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="sync_nuvio_watch_history").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0003_disable_sync_nuvio_playback_schedule"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
