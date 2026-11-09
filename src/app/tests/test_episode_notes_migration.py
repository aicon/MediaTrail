import importlib
from datetime import UTC, datetime

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import IntegrityError
from django.test import TransactionTestCase

from app.models import Episode

NOTES_MIGRATION = "0063_episode_notes_when_missing"
BEFORE_NOTES = "0062_truncate_media_date_seconds"
TABLES = ("app_episode", "app_historicalepisode")


def column_names(table):
    """Return the column names currently stored for one table."""
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return [column.name for column in description]


def drop_notes(table):
    """Remove notes so the migration has to create it."""
    if "notes" not in column_names(table):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {table} DROP COLUMN notes")


class EpisodeNotesMigrationTests(TransactionTestCase):
    """The notes column must appear on a new database and be left alone on an old one."""

    def test_models_and_migration_state_include_notes(self):
        """Episode, its history model, and the migration state all define notes."""
        for model in (Episode, Episode.history.model):
            field = model._meta.get_field("notes")
            self.assertEqual(field.default, "")
            self.assertTrue(field.blank)
            self.assertFalse(field.null)

        state = MigrationExecutor(connection).loader.project_state()
        for model_name in ("Episode", "HistoricalEpisode"):
            field = state.apps.get_model("app", model_name)._meta.get_field("notes")
            self.assertEqual(field.default, "")
            self.assertFalse(field.null)

    def test_missing_column_is_added_and_existing_column_is_kept(self):
        """Cover a database without notes and one where notes was added already."""
        executor = MigrationExecutor(connection)
        leaf = executor.loader.graph.leaf_nodes()
        try:
            self._migrate(executor, BEFORE_NOTES)
            for table in TABLES:
                drop_notes(table)
                self.assertNotIn("notes", column_names(table))

            self._migrate(executor, NOTES_MIGRATION)
            for table in TABLES:
                self.assertIn("notes", column_names(table))
            self.assert_empty_notes_can_be_stored()

            # Reverse does not drop the column, matching a database migrated by 0065.
            self._migrate(executor, BEFORE_NOTES)
            for table in TABLES:
                self.assertIn("notes", column_names(table))

            self._migrate(executor, NOTES_MIGRATION)
            for table in TABLES:
                self.assertEqual(column_names(table).count("notes"), 1)
            self.assert_empty_notes_can_be_stored()
        finally:
            executor.loader.build_graph()
            executor.migrate(leaf)

    def _migrate(self, executor, migration_name):
        executor.loader.build_graph()
        executor.migrate([("app", migration_name)])

    def assert_empty_notes_can_be_stored(self):
        """A history insert with an empty note succeeds, and NULL still does not."""
        now = datetime.now(UTC).isoformat()
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
            with self.assertRaises(IntegrityError):
                cursor.execute(
                    "INSERT INTO app_episode "
                    "(item_id, related_season_id, end_date, notes, created_at) "
                    "VALUES (1, 1, %s, NULL, %s)",
                    [now, now],
                )
            connection.rollback()
            cursor.execute(
                "INSERT INTO app_episode "
                "(item_id, related_season_id, end_date, notes, created_at) "
                "VALUES (1, 1, %s, %s, %s)",
                [now, "", now],
            )
            cursor.execute(
                "SELECT notes FROM app_episode WHERE item_id=1 AND related_season_id=1",
            )
            stored = cursor.fetchone()
            cursor.execute(
                "DELETE FROM app_episode WHERE item_id=1 AND related_season_id=1",
            )
        self.assertEqual(stored[0], "")


# Importing the migration module checks that it stays loadable with the test app.
importlib.import_module("app.migrations.0063_episode_notes_when_missing")
