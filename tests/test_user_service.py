"""Tests for creating and normalizing users."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select

from fatura_parser.auth import (
    InvalidEmailError,
    UserAlreadyExistsError,
    create_user,
    normalize_email,
)
from fatura_parser.database import DatabaseBase, User, create_database


class UserServiceTests(unittest.TestCase):
    """Verify account creation rules independently from the HTTP API."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        database_path = Path(self.temporary_directory.name) / "test.db"
        self.database = create_database(database_path)
        self.addCleanup(self.database.close)
        DatabaseBase.metadata.create_all(self.database.engine)

    def test_normalizes_an_email_without_a_network_lookup(self) -> None:
        self.assertEqual(
            normalize_email("Chris@EXAMPLE.COM"),
            "Chris@example.com",
        )

    def test_rejects_an_invalid_email(self) -> None:
        with self.assertRaises(InvalidEmailError):
            normalize_email("not-an-email")

    def test_creates_a_user_without_storing_the_plaintext_password(self) -> None:
        password = "uma frase senha longa"

        with self.database.session_factory() as session:
            user = create_user(
                session,
                email="Chris@EXAMPLE.COM",
                password=password,
            )
            session.commit()
            user_id = user.id

        with self.database.session_factory() as session:
            saved_user = session.scalar(
                select(User).where(User.id == user_id)
            )

        self.assertIsNotNone(saved_user)
        assert saved_user is not None
        self.assertEqual(saved_user.email, "Chris@example.com")
        self.assertTrue(saved_user.password_hash.startswith("$argon2id$"))
        self.assertNotIn(password, saved_user.password_hash)

    def test_rejects_an_email_that_is_already_registered(self) -> None:
        with self.database.session_factory() as session:
            create_user(
                session,
                email="chris@example.com",
                password="primeira frase senha longa",
            )
            session.commit()

            with self.assertRaises(UserAlreadyExistsError):
                create_user(
                    session,
                    email="CHRIS@example.com",
                    password="segunda frase senha longa",
                )
