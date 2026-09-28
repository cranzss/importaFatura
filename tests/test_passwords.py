"""Tests for password hashing and verification."""

import unittest

from argon2 import PasswordHasher
from argon2.low_level import Type

from fatura_parser.auth.passwords import (
    InvalidPasswordError,
    PasswordManager,
)


class PasswordManagerTests(unittest.TestCase):
    """Verify that plaintext passwords are handled safely."""

    def test_hashes_with_argon2id_and_a_random_salt(self) -> None:
        manager = PasswordManager()
        password = "uma frase senha longa"

        first_hash = manager.hash(password)
        second_hash = manager.hash(password)

        self.assertTrue(first_hash.startswith("$argon2id$"))
        self.assertNotEqual(first_hash, second_hash)
        self.assertNotIn(password, first_hash)

    def test_verifies_the_correct_password(self) -> None:
        manager = PasswordManager()
        password_hash = manager.hash("uma frase senha longa")

        verification = manager.verify(
            "uma frase senha longa",
            password_hash,
        )

        self.assertTrue(verification.valid)
        self.assertIsNone(verification.replacement_hash)

    def test_rejects_an_incorrect_or_invalid_hash(self) -> None:
        manager = PasswordManager()
        password_hash = manager.hash("uma frase senha longa")

        self.assertFalse(
            manager.verify("senha totalmente errada", password_hash).valid
        )
        self.assertFalse(manager.verify("qualquer senha", "invalid").valid)

    def test_prepares_a_replacement_for_an_outdated_hash(self) -> None:
        old_hasher = PasswordHasher(
            time_cost=1,
            memory_cost=8,
            parallelism=1,
            hash_len=16,
            salt_len=8,
            type=Type.ID,
        )
        password = "uma frase senha longa"
        old_hash = old_hasher.hash(password)

        verification = PasswordManager().verify(password, old_hash)

        self.assertTrue(verification.valid)
        self.assertIsNotNone(verification.replacement_hash)
        assert verification.replacement_hash is not None
        self.assertTrue(verification.replacement_hash.startswith("$argon2id$"))

    def test_requires_between_15_and_128_characters(self) -> None:
        manager = PasswordManager()

        with self.assertRaises(InvalidPasswordError):
            manager.hash("curta demais")
        with self.assertRaises(InvalidPasswordError):
            manager.hash("x" * 129)

    def test_normalizes_unicode_consistently(self) -> None:
        manager = PasswordManager()
        decomposed_password = "cafe\u0301 com uma senha longa"
        composed_password = "café com uma senha longa"

        password_hash = manager.hash(decomposed_password)

        self.assertTrue(manager.verify(composed_password, password_hash).valid)
