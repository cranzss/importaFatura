"""Dependencies shared by HTTP API routes."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from fatura_parser.database import Database


def get_database_session(request: Request) -> Iterator[Session]:
    """Provide one SQLAlchemy session for the lifetime of a request."""
    database: Database = request.app.state.database

    with database.session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
