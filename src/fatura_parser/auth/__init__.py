"""Public interface for local user credentials."""

from fatura_parser.auth.passwords import (
    InvalidPasswordError,
    PasswordManager,
    PasswordVerification,
)
from fatura_parser.auth.sessions import (
    DEFAULT_SESSION_LIFETIME,
    SessionToken,
    create_user_session,
    delete_expired_sessions,
    resolve_session_user,
    revoke_user_session,
)
from fatura_parser.auth.users import (
    InvalidEmailError,
    UserAlreadyExistsError,
    authenticate_user,
    create_user,
    normalize_email,
)


__all__ = [
    "InvalidEmailError",
    "InvalidPasswordError",
    "DEFAULT_SESSION_LIFETIME",
    "PasswordManager",
    "PasswordVerification",
    "SessionToken",
    "UserAlreadyExistsError",
    "authenticate_user",
    "create_user",
    "create_user_session",
    "delete_expired_sessions",
    "normalize_email",
    "resolve_session_user",
    "revoke_user_session",
]
