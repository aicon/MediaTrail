from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0059_user_nuvio_sync_library"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="emby_server_url",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Emby server origin used to read active sessions",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="emby_api_key",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Encrypted Emby API key for session polling",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="emby_user_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Stable Emby user id whose sessions may drive Now Watching",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="emby_user_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Emby user name shown in settings; not used for authorization",
                max_length=150,
            ),
        ),
    ]
