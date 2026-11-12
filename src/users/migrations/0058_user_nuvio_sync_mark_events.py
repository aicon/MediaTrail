from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0057_user_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="nuvio_sync_mark_played_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Sync Nuvio mark-watched changes with MediaTrail watch history",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="nuvio_sync_mark_unplayed_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Sync Nuvio mark-unwatched changes with MediaTrail watch history",
            ),
        ),
    ]
