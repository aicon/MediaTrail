from django.db import migrations, models


class Migration(migrations.Migration):
    """Persist mid-watch episode resume on Season (+ Movie resume_updated_at)."""

    dependencies = [
        ("app", "0071_movie_resume_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalmovie",
            name="resume_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="movie",
            name="resume_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalseason",
            name="resume_duration_ms",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalseason",
            name="resume_episode_number",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalseason",
            name="resume_position_ms",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalseason",
            name="resume_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="resume_duration_ms",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="resume_episode_number",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="resume_position_ms",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="season",
            name="resume_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
