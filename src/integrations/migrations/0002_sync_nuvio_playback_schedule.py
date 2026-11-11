from django.db import migrations


def create_schedule(apps, schema_editor):
    """Keep Now Watching in sync with Nuvio Sync every 30 seconds."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _created = IntervalSchedule.objects.get_or_create(
        every=30,
        period="seconds",
    )
    PeriodicTask.objects.update_or_create(
        name="sync_nuvio_playback",
        defaults={
            "task": "Sync Nuvio playback",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="sync_nuvio_playback").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_nuvioaccount"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
