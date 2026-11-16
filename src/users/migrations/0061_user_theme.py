from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0060_user_emby_live"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="theme",
            field=models.CharField(
                choices=[
                    ("system", "System"),
                    ("light", "Light"),
                    ("dark", "Dark"),
                ],
                default="dark",
                help_text="Interface appearance. System follows the device color scheme.",
                max_length=8,
            ),
        ),
    ]
