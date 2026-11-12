# Stable Now Watching strip order: created_at index for list queries.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Index live rows by first-seen time for stable home ordering."""

    dependencies = [
        ("app", "0068_liveplayback_device"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="liveplayback",
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="liveplayback",
            index=models.Index(
                fields=["user", "created_at"],
                name="app_livepb_user_created_idx",
            ),
        ),
    ]
