from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0063_user_detail_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="rec_tmdb_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="rec_imdb_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="rec_ai_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="gemini_api_key",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Encrypted Gemini API key for AI recommendations",
            ),
        ),
    ]
