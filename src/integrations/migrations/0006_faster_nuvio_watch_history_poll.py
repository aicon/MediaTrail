from django.db import migrations


def update_schedules(apps, schema_editor):
    """Poll Nuvio deltas often; run a full snapshot reconcile less often."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    fast, _created = IntervalSchedule.objects.get_or_create(
        every=30,
        period="seconds",
    )
    PeriodicTask.objects.update_or_create(
        name="sync_nuvio_watch_history",
        defaults={
            "task": "Sync Nuvio watch history",
            "interval": fast,
            "enabled": True,
        },
    )
    slow, _created = IntervalSchedule.objects.get_or_create(
        every=15,
        period="minutes",
    )
    PeriodicTask.objects.update_or_create(
        name="reconcile_nuvio_watch_history",
        defaults={
            "task": "Reconcile Nuvio watch history",
            "interval": slow,
            "enabled": True,
        },
    )


def restore_schedules(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="reconcile_nuvio_watch_history").delete()
    five_min, _created = IntervalSchedule.objects.get_or_create(
        every=5,
        period="minutes",
    )
    PeriodicTask.objects.update_or_create(
        name="sync_nuvio_watch_history",
        defaults={
            "task": "Sync Nuvio watch history",
            "interval": five_min,
            "enabled": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0005_nuvioaccount_watched_keys"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(update_schedules, restore_schedules),
    ]
