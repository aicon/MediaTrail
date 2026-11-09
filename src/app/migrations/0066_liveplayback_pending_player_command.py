from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0065_liveplayback_display_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveplayback",
            name="pending_player_command",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
