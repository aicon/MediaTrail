from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0058_user_nuvio_sync_mark_events"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="nuvio_sync_library_enabled",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Two-way sync between the Nuvio Library and a designated "
                    "MediaTrail watchlist"
                ),
            ),
        ),
    ]
