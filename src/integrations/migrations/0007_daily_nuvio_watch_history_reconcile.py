from django.db import migrations


def update_reconcile_schedule(apps, schema_editor):
    """Keep 30s deltas; run full snapshot reconcile once per day."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    daily, _created = IntervalSchedule.objects.get_or_create(
        every=24,
        period="hours",
    )
    PeriodicTask.objects.update_or_create(
        name="reconcile_nuvio_watch_history",
        defaults={
            "task": "Reconcile Nuvio watch history",
            "interval": daily,
            "enabled": True,
        },
    )


def restore_reconcile_schedule(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
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


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0006_faster_nuvio_watch_history_poll"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(update_reconcile_schedule, restore_reconcile_schedule),
    ]
