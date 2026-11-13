from django.db import migrations


def update_schedules(apps, schema_editor):
    """Poll Nuvio library deltas on the same cadence as watch-history."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    fast, _created = IntervalSchedule.objects.get_or_create(
        every=30,
        period="seconds",
    )
    PeriodicTask.objects.update_or_create(
        name="sync_nuvio_library",
        defaults={
            "task": "Sync Nuvio library",
            "interval": fast,
            "enabled": True,
        },
    )


def restore_schedules(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="sync_nuvio_library").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0008_nuvioaccount_library_watchlist"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(update_schedules, restore_schedules),
    ]
