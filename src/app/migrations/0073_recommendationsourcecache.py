from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0072_season_episode_resume"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecommendationSourceCache",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("source", models.CharField(max_length=16)),
                ("media_type", models.CharField(max_length=20)),
                ("seed_key", models.CharField(max_length=64)),
                ("user_id", models.PositiveIntegerField(default=0)),
                ("payload", models.JSONField(default=list)),
                ("fetched_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="recommendationsourcecache",
            constraint=models.UniqueConstraint(
                fields=("source", "media_type", "seed_key", "user_id"),
                name="unique_recommendation_source_cache",
            ),
        ),
    ]
