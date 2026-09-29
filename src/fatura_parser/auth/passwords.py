"""Hash and verify passwords without persisting their plaintext value."""

from dataclasses import dataclass
from unicodedata import normalize

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class InvalidPasswordError(ValueError):
    """Raised when a new password does not satisfy the local policy."""


@dataclass(frozen=True, slots=True)
class PasswordVerification:
    """Result of checking a plaintext password against an encoded hash."""

    valid: bool
    replacement_hash: str | None = None


class PasswordManager:
    """Provide the application's high-level Argon2id operations."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher()

    def hash(self, password: str) -> str:
        """Validate and hash a new password using a random salt."""
        normalized_password = _normalize_password(password)
        _validate_new_password(normalized_password)
        return self._hasher.hash(normalized_password)

    def verify(
        self,
        password: str,
        password_hash: str,
    ) -> PasswordVerification:
        """Verify a password and prepare a stronger hash when needed."""
        normalized_password = _normalize_password(password)

        try:
            self._hasher.verify(password_hash, normalized_password)
        except (InvalidHashError, VerificationError):
            return PasswordVerification(valid=False)

        replacement_hash = None
        if self._hasher.check_needs_rehash(password_hash):
            replacement_hash = self._hasher.hash(normalized_password)

        return PasswordVerification(
            valid=True,
            replacement_hash=replacement_hash,
        )


def _normalize_password(password: str) -> str:
    """Return the NFC representation used consistently by hash and verify."""
    if not isinstance(password, str):
        raise InvalidPasswordError("password must be text")
    return normalize("NFC", password)


def _validate_new_password(password: str) -> None:
    """Enforce length without requiring arbitrary character categories."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"password must contain at least {MIN_PASSWORD_LENGTH} characters"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"password must contain at most {MAX_PASSWORD_LENGTH} characters"
        )
