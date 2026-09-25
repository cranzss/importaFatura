"""Create and configure the local SQLite database infrastructure."""

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DEFAULT_DATABASE_PATH = Path("data") / "fatura_parser.db"
_BUSY_TIMEOUT_MILLISECONDS = 5_000


class DatabaseBase(DeclarativeBase):
    """Base class inherited by every SQLAlchemy table model."""


@dataclass(frozen=True, slots=True)
class Database:
    """Database resources shared by the application."""

    engine: Engine
    session_factory: sessionmaker[Session]

    def close(self) -> None:
        """Release every pooled SQLite connection."""
        self.engine.dispose()


def _configure_sqlite_connection(
    dbapi_connection: SQLiteConnection,
    _connection_record: object,
) -> None:
    """Enable integrity and concurrency settings on each connection."""
    previous_autocommit = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute(
            f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MILLISECONDS}"
        )
    finally:
        cursor.close()
        dbapi_connection.autocommit = previous_autocommit


def create_database(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> Database:
    """Create the engine and session factory for one local SQLite file."""
    resolved_path = Path(database_path).expanduser().resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        URL.create(
            drivername="sqlite+pysqlite",
            database=str(resolved_path),
        ),
        connect_args={
            "autocommit": False,
            "check_same_thread": False,
            "timeout": _BUSY_TIMEOUT_MILLISECONDS / 1_000,
        },
    )
    event.listen(engine, "connect", _configure_sqlite_connection)

    database = Database(
        engine=engine,
        session_factory=sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
        ),
    )

    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except Exception:
        database.close()
        raise

    return database
