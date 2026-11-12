from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0004_sync_nuvio_watch_history_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="nuvioaccount",
            name="watched_keys",
            field=models.JSONField(
                default=list,
                help_text="Last Nuvio watch-history snapshot keys for unwatch reconcile",
            ),
        ),
    ]
