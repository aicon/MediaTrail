from django.db import migrations, models


class Migration(migrations.Migration):
    """Persist mid-watch movie resume for the home In Progress list."""

    dependencies = [
        ("app", "0070_restore_tz_shifted_media_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalmovie",
            name="resume_duration_ms",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalmovie",
            name="resume_position_ms",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="movie",
            name="resume_duration_ms",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="movie",
            name="resume_position_ms",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
    ]
