"""Tests for the database user model."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from fatura_parser.database import DatabaseBase, User, create_database


class UserModelTests(unittest.TestCase):
    """Verify the model mapping and database constraints."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "test.db"
        self.database = create_database(database_path)
        DatabaseBase.metadata.create_all(self.database.engine)

    def tearDown(self) -> None:
        self.database.close()
        self.temporary_directory.cleanup()

    def test_persists_user_with_database_defaults(self) -> None:
        user = User(
            email="chris@example.com",
            password_hash="$argon2id$example-hash",
        )

        with self.database.session_factory() as session:
            session.add(user)
            session.commit()
            session.refresh(user)

        self.assertIsInstance(user.id, int)
        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.created_at)

    def test_email_uniqueness_is_case_insensitive(self) -> None:
        with self.database.session_factory() as session:
            session.add(
                User(
                    email="chris@example.com",
                    password_hash="$argon2id$first-hash",
                )
            )
            session.commit()

            session.add(
                User(
                    email="CHRIS@example.com",
                    password_hash="$argon2id$second-hash",
                )
            )

            with self.assertRaises(IntegrityError):
                session.commit()

    def test_can_query_user_by_email(self) -> None:
        with self.database.session_factory() as session:
            session.add(
                User(
                    email="chris@example.com",
                    password_hash="$argon2id$example-hash",
                )
            )
            session.commit()

            saved_user = session.scalar(
                select(User).where(User.email == "chris@example.com")
            )

        self.assertIsNotNone(saved_user)
        assert saved_user is not None
        self.assertEqual(saved_user.email, "chris@example.com")
