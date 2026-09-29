"""Create and normalize local application users."""

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fatura_parser.auth.passwords import InvalidPasswordError, PasswordManager
from fatura_parser.database import User


_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "+nqi29KfJ4OxVSpAhxzNqg$"
    "c4HNVVwc2c1qX8GRC+PbAuSRULWw17HnF6pHnFdiJkk"
)


class InvalidEmailError(ValueError):
    """Raised when an email cannot safely identify a local user."""


class UserAlreadyExistsError(ValueError):
    """Raised when the normalized email is already registered."""


def normalize_email(email: str) -> str:
    """Validate an email and return its canonical representation."""
    try:
        email_information = validate_email(
            email,
            check_deliverability=False,
        )
    except (EmailNotValidError, TypeError) as error:
        raise InvalidEmailError("invalid email address") from error

    return email_information.normalized


def create_user(
    session: Session,
    *,
    email: str,
    password: str,
    password_manager: PasswordManager | None = None,
) -> User:
    """Add a new user to the current transaction."""
    normalized_email = normalize_email(email)

    existing_user_id = session.scalar(
        select(User.id).where(User.email == normalized_email)
    )
    if existing_user_id is not None:
        raise UserAlreadyExistsError("email is already registered")

    manager = password_manager or PasswordManager()
    user = User(
        email=normalized_email,
        password_hash=manager.hash(password),
    )
    session.add(user)

    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise UserAlreadyExistsError(
            "email is already registered"
        ) from error

    return user


def authenticate_user(
    session: Session,
    *,
    email: str,
    password: str,
    password_manager: PasswordManager | None = None,
) -> User | None:
    """Return an active user only when both credentials are valid."""
    manager = password_manager or PasswordManager()

    try:
        normalized_email = normalize_email(email)
    except InvalidEmailError:
        normalized_email = None

    user = (
        session.scalar(select(User).where(User.email == normalized_email))
        if normalized_email is not None
        else None
    )
    password_hash = (
        user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    )

    try:
        verification = manager.verify(password, password_hash)
    except InvalidPasswordError:
        return None

    if user is None or not user.is_active or not verification.valid:
        return None

    if verification.replacement_hash is not None:
        user.password_hash = verification.replacement_hash
        session.flush()

    return user
