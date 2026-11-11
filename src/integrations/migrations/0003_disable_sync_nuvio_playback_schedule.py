from django.db import migrations


def disable_schedule(apps, schema_editor):
    """Now Watching comes from addon player events, not Nuvio Sync polling."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="sync_nuvio_playback").update(enabled=False)


def enable_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="sync_nuvio_playback").update(enabled=True)


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0002_sync_nuvio_playback_schedule"),
    ]

    operations = [
        migrations.RunPython(disable_schedule, enable_schedule),
    ]
