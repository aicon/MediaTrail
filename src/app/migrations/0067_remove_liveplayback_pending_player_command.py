from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0066_liveplayback_pending_player_command"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="liveplayback",
            name="pending_player_command",
        ),
    ]
