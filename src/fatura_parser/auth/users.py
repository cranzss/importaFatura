"""Create and normalize local application users."""

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fatura_parser.auth.passwords import PasswordManager
from fatura_parser.database import User


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
