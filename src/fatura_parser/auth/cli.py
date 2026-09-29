"""Secure command-line entry point for creating a local user."""

from argparse import ArgumentParser
from collections.abc import Sequence
from getpass import getpass
from pathlib import Path

from sqlalchemy.exc import OperationalError

from fatura_parser.auth.passwords import InvalidPasswordError
from fatura_parser.auth.users import (
    InvalidEmailError,
    UserAlreadyExistsError,
    create_user,
)
from fatura_parser.database import DEFAULT_DATABASE_PATH, create_database


class UserCreationError(Exception):
    """Raised for an expected failure while creating a local user."""


def create_local_user(
    email: str,
    password: str,
    *,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> str:
    """Persist one user and return the normalized email address."""
    database = create_database(database_path)
    try:
        with database.session_factory() as session:
            try:
                user = create_user(
                    session,
                    email=email,
                    password=password,
                )
                session.commit()
            except OperationalError as error:
                session.rollback()
                raise UserCreationError(
                    "database schema is not ready; run "
                    "'python -m alembic upgrade head' first"
                ) from error

            return user.email
    finally:
        database.close()


def build_argument_parser() -> ArgumentParser:
    """Create arguments accepted by the local user command."""
    parser = ArgumentParser(
        allow_abbrev=False,
        description="Cria um usuário local sem expor sua senha.",
    )
    parser.add_argument("email", help="E-mail usado para entrar na aplicação.")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Caminho do banco SQLite local.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Prompt for a password and create the requested local user."""
    argument_parser = build_argument_parser()
    parsed_arguments = argument_parser.parse_args(arguments)
    password = getpass("Senha: ")
    password_confirmation = getpass("Confirme a senha: ")

    if password != password_confirmation:
        argument_parser.error("as senhas informadas são diferentes")

    try:
        normalized_email = create_local_user(
            parsed_arguments.email,
            password,
            database_path=parsed_arguments.database,
        )
    except (
        InvalidEmailError,
        InvalidPasswordError,
        UserAlreadyExistsError,
        UserCreationError,
    ) as error:
        argument_parser.error(str(error))

    print(f"Usuário criado: {normalized_email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
