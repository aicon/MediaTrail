from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NuvioAccount",
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
                ("email", models.TextField()),
                ("password", models.TextField()),
                ("profile_id", models.PositiveIntegerField(default=1)),
                ("cursor", models.BigIntegerField(blank=True, null=True)),
                ("bootstrapped", models.BooleanField(default=False)),
                ("imported_ids", models.JSONField(default=list)),
                ("permanent_ids", models.JSONField(default=list)),
                ("imdb_map", models.JSONField(default=dict)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="nuvio_account",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
