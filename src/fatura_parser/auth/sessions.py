"""Create, resolve, and revoke opaque server-side login sessions."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fatura_parser.database import User, UserSession


SESSION_TOKEN_BYTES = 32
MAX_ACCEPTED_TOKEN_LENGTH = 256
DEFAULT_SESSION_LIFETIME = timedelta(hours=12)


@dataclass(frozen=True, slots=True)
class SessionToken:
    """Secret returned once to the client when a session is created."""

    value: str
    expires_at: datetime


def create_user_session(
    session: Session,
    *,
    user_id: int,
    lifetime: timedelta = DEFAULT_SESSION_LIFETIME,
    now: datetime | None = None,
) -> SessionToken:
    """Persist a token hash and return its unguessable plaintext value."""
    if lifetime <= timedelta(0):
        raise ValueError("session lifetime must be positive")

    current_time = _as_utc_naive(now or datetime.now(UTC))
    expires_at = current_time + lifetime
    token = token_urlsafe(SESSION_TOKEN_BYTES)
    stored_session = UserSession(
        user_id=user_id,
        token_hash=_hash_token(token),
        created_at=current_time,
        expires_at=expires_at,
    )
    session.add(stored_session)
    session.flush()

    return SessionToken(value=token, expires_at=expires_at)


def resolve_session_user(
    session: Session,
    token: str,
    *,
    now: datetime | None = None,
) -> User | None:
    """Return the active user for a valid and unexpired token."""
    token_hash = _accepted_token_hash(token)
    if token_hash is None:
        return None

    current_time = _as_utc_naive(now or datetime.now(UTC))
    return session.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > current_time,
            User.is_active.is_(True),
        )
    )


def revoke_user_session(session: Session, token: str) -> bool:
    """Delete a session by token and report whether one existed."""
    token_hash = _accepted_token_hash(token)
    if token_hash is None:
        return False

    result = session.execute(
        delete(UserSession).where(UserSession.token_hash == token_hash)
    )
    return bool(result.rowcount)


def delete_expired_sessions(
    session: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Remove expired rows so the local database does not grow forever."""
    current_time = _as_utc_naive(now or datetime.now(UTC))
    result = session.execute(
        delete(UserSession).where(UserSession.expires_at <= current_time)
    )
    return result.rowcount or 0


def _accepted_token_hash(token: str) -> str | None:
    """Bound untrusted cookie input before hashing it."""
    if not isinstance(token, str):
        return None
    if not token or len(token) > MAX_ACCEPTED_TOKEN_LENGTH:
        return None
    return _hash_token(token)


def _hash_token(token: str) -> str:
    """Return the fixed-size representation persisted in SQLite."""
    return sha256(token.encode("utf-8")).hexdigest()


def _as_utc_naive(value: datetime) -> datetime:
    """Represent UTC consistently because SQLite has no timezone type."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
