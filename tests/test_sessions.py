"""Tests for opaque server-side login sessions."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import select

from fatura_parser.auth.sessions import (
    create_user_session,
    delete_expired_sessions,
    resolve_session_user,
    revoke_user_session,
)
from fatura_parser.database import (
    DatabaseBase,
    User,
    UserSession,
    create_database,
)


class SessionServiceTests(unittest.TestCase):
    """Verify session secrecy, expiration, and revocation."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        database_path = Path(self.temporary_directory.name) / "test.db"
        self.database = create_database(database_path)
        self.addCleanup(self.database.close)
        DatabaseBase.metadata.create_all(self.database.engine)

        with self.database.session_factory() as session:
            user = User(
                email="chris@example.com",
                password_hash="$argon2id$example-hash",
            )
            session.add(user)
            session.commit()
            self.user_id = user.id

    def test_stores_only_the_hash_of_a_random_256_bit_token(self) -> None:
        now = datetime(2026, 9, 28, 12, tzinfo=UTC)

        with self.database.session_factory() as session:
            credentials = create_user_session(
                session,
                user_id=self.user_id,
                now=now,
            )
            session.commit()
            stored_session = session.scalar(select(UserSession))

        self.assertIsNotNone(stored_session)
        assert stored_session is not None
        self.assertGreaterEqual(len(credentials.value), 43)
        self.assertNotEqual(stored_session.token_hash, credentials.value)
        self.assertEqual(
            stored_session.token_hash,
            sha256(credentials.value.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            credentials.expires_at,
            datetime(2026, 9, 29, 0),
        )

    def test_creates_a_different_token_for_each_session(self) -> None:
        with self.database.session_factory() as session:
            first = create_user_session(session, user_id=self.user_id)
            second = create_user_session(session, user_id=self.user_id)

        self.assertNotEqual(first.value, second.value)

    def test_resolves_only_an_active_unexpired_session(self) -> None:
        now = datetime(2026, 9, 28, 12, tzinfo=UTC)

        with self.database.session_factory() as session:
            credentials = create_user_session(
                session,
                user_id=self.user_id,
                lifetime=timedelta(hours=1),
                now=now,
            )
            session.commit()

            active_user = resolve_session_user(
                session,
                credentials.value,
                now=now + timedelta(minutes=59),
            )
            expired_user = resolve_session_user(
                session,
                credentials.value,
                now=now + timedelta(hours=1),
            )

        self.assertIsNotNone(active_user)
        self.assertIsNone(expired_user)

    def test_rejects_a_session_for_a_disabled_user(self) -> None:
        with self.database.session_factory() as session:
            credentials = create_user_session(
                session,
                user_id=self.user_id,
            )
            user = session.get(User, self.user_id)
            assert user is not None
            user.is_active = False
            session.commit()

            resolved_user = resolve_session_user(
                session,
                credentials.value,
            )

        self.assertIsNone(resolved_user)

    def test_deleting_a_user_cascades_to_its_sessions(self) -> None:
        with self.database.session_factory() as session:
            create_user_session(session, user_id=self.user_id)
            session.commit()

            user = session.get(User, self.user_id)
            assert user is not None
            session.delete(user)
            session.commit()

            self.assertEqual(
                len(session.scalars(select(UserSession)).all()),
                0,
            )

    def test_revokes_a_session_without_exposing_whether_a_token_exists(self) -> None:
        with self.database.session_factory() as session:
            credentials = create_user_session(
                session,
                user_id=self.user_id,
            )
            session.commit()

            self.assertTrue(revoke_user_session(session, credentials.value))
            self.assertFalse(revoke_user_session(session, credentials.value))
            session.commit()

            self.assertIsNone(
                resolve_session_user(session, credentials.value)
            )

    def test_rejects_invalid_token_input(self) -> None:
        with self.database.session_factory() as session:
            self.assertIsNone(resolve_session_user(session, ""))
            self.assertIsNone(resolve_session_user(session, "x" * 257))
            self.assertFalse(revoke_user_session(session, ""))

    def test_deletes_expired_sessions(self) -> None:
        now = datetime(2026, 9, 28, 12, tzinfo=UTC)

        with self.database.session_factory() as session:
            create_user_session(
                session,
                user_id=self.user_id,
                lifetime=timedelta(minutes=1),
                now=now,
            )
            create_user_session(
                session,
                user_id=self.user_id,
                lifetime=timedelta(hours=1),
                now=now,
            )
            session.commit()

            deleted_count = delete_expired_sessions(
                session,
                now=now + timedelta(minutes=2),
            )
            session.commit()
            remaining_count = len(session.scalars(select(UserSession)).all())

        self.assertEqual(deleted_count, 1)
        self.assertEqual(remaining_count, 1)

    def test_requires_a_positive_lifetime(self) -> None:
        with self.database.session_factory() as session:
            with self.assertRaises(ValueError):
                create_user_session(
                    session,
                    user_id=self.user_id,
                    lifetime=timedelta(0),
                )
