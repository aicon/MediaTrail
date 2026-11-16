from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0061_user_theme"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="language",
            field=models.CharField(
                choices=[
                    ("auto", "Auto (browser language)"),
                    ("de", "Deutsch"),
                    ("en", "English"),
                    ("es", "Español"),
                    ("fr", "Français"),
                    ("hu", "Magyar"),
                    ("it", "Italiano"),
                ],
                default="auto",
                max_length=8,
            ),
        ),
    ]
