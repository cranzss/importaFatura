"""Tests for the Alembic database migrations."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    """Verify that schema migrations can be applied and reverted."""

    def test_schema_migrations_upgrade_and_downgrade(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "migration.db"
            config = Config(PROJECT_ROOT / "alembic.ini")
            database_url = URL.create(
                drivername="sqlite+pysqlite",
                database=str(database_path),
            ).render_as_string(hide_password=False)
            config.set_main_option(
                "sqlalchemy.url",
                database_url.replace("%", "%%"),
            )

            command.upgrade(config, "head")
            command.check(config)

            engine = create_engine(
                URL.create(
                    drivername="sqlite+pysqlite",
                    database=str(database_path),
                )
            )
            try:
                inspector = inspect(engine)
                self.assertIn("users", inspector.get_table_names())
                self.assertIn("user_sessions", inspector.get_table_names())
                self.assertEqual(
                    {column["name"] for column in inspector.get_columns("users")},
                    {
                        "id",
                        "email",
                        "password_hash",
                        "is_active",
                        "created_at",
                    },
                )
                self.assertEqual(
                    inspector.get_unique_constraints("users")[0]["column_names"],
                    ["email"],
                )
                self.assertEqual(
                    inspector.get_unique_constraints("user_sessions")[0][
                        "column_names"
                    ],
                    ["token_hash"],
                )
            finally:
                engine.dispose()

            command.downgrade(config, "base")

            downgraded_engine = create_engine(
                URL.create(
                    drivername="sqlite+pysqlite",
                    database=str(database_path),
                )
            )
            try:
                self.assertNotIn(
                    "users",
                    inspect(downgraded_engine).get_table_names(),
                )
            finally:
                downgraded_engine.dispose()
