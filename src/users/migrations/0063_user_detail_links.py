from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0062_user_language_auto"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="link_imdb_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="link_wikidata_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="link_trakt_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="link_letterboxd_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="link_tvdb_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="link_simkl_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="link_port_hu_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
