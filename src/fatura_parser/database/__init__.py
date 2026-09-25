"""Public interface for the database infrastructure."""

from fatura_parser.database.core import (
    DEFAULT_DATABASE_PATH,
    Database,
    DatabaseBase,
    create_database,
)


__all__ = [
    "DEFAULT_DATABASE_PATH",
    "Database",
    "DatabaseBase",
    "create_database",
]
