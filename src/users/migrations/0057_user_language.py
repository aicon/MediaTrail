from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0056_user_home_hide_unreleased"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="language",
            field=models.CharField(
                choices=[("en", "English"), ("hu", "Magyar")],
                default="en",
                max_length=8,
            ),
        ),
    ]
