from django.db import migrations, models


def add_notes_if_missing(apps, schema_editor):
    """Add notes only when this database was created before the column existed.

    A newer Yamtrack release may already have applied its own notes migration.
    Adding the column again would abort startup.
    """
    connection = schema_editor.connection
    for model_name in ("Episode", "HistoricalEpisode"):
        model = apps.get_model("app", model_name)
        table = model._meta.db_table
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table)
        if any(column.name == "notes" for column in description):
            continue
        field = models.TextField(blank=True, default="")
        field.set_attributes_from_name("notes")
        schema_editor.add_field(model, field)


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0062_truncate_media_date_seconds"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="episode",
                    name="notes",
                    field=models.TextField(blank=True, default=""),
                ),
                migrations.AddField(
                    model_name="historicalepisode",
                    name="notes",
                    field=models.TextField(blank=True, default=""),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_notes_if_missing, migrations.RunPython.noop),
            ],
        ),
    ]
