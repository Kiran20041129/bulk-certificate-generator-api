"""Database engine and session setup (SQLAlchemy 2.0)."""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Parent class of all database models."""


def create_db_engine(database_url: str) -> Engine:
    """Create an engine. SQLite gets a few settings that make it behave well."""
    if not database_url.startswith("sqlite"):
        return create_engine(database_url)

    engine = create_engine(
        database_url,
        # The API thread and the background-job thread both use the DB.
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")   # SQLite ignores FKs by default
        cursor.execute("PRAGMA journal_mode=WAL")  # status polling while writing
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine = create_db_engine(get_settings().database_url)
SessionLocal = create_session_factory(engine)
