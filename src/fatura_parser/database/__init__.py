"""Public interface for the database infrastructure."""

from fatura_parser.database.core import (
    DEFAULT_DATABASE_PATH,
    Database,
    DatabaseBase,
    create_database,
)
from fatura_parser.database.models import User


__all__ = [
    "DEFAULT_DATABASE_PATH",
    "Database",
    "DatabaseBase",
    "User",
    "create_database",
]
