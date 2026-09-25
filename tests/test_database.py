from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import text

from fatura_parser.database import create_database


class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database_path = (
            Path(self.temporary_directory.name)
            / "nested"
            / "test.db"
        )

    def test_creates_a_working_session_for_the_sqlite_file(self) -> None:
        database = create_database(self.database_path)
        self.addCleanup(database.close)

        with database.session_factory() as session:
            result = session.scalar(text("SELECT 1"))

        self.assertEqual(result, 1)
        self.assertTrue(self.database_path.exists())

    def test_enables_sqlite_integrity_and_concurrency_settings(self) -> None:
        database = create_database(self.database_path)
        self.addCleanup(database.close)

        with database.engine.connect() as connection:
            foreign_keys = connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar_one()
            journal_mode = connection.exec_driver_sql(
                "PRAGMA journal_mode"
            ).scalar_one()
            busy_timeout = connection.exec_driver_sql(
                "PRAGMA busy_timeout"
            ).scalar_one()

        self.assertEqual(foreign_keys, 1)
        self.assertEqual(journal_mode, "wal")
        self.assertEqual(busy_timeout, 5_000)


if __name__ == "__main__":
    unittest.main()
