"""חיבור DB — SQLite מקומי (תואם PostgreSQL להמשך)."""
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_engine = None
_SessionLocal: sessionmaker | None = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        url = settings.database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def _add_column_if_missing(table: str, column: str, ddl_type: str):
    """create_all לא מוסיף עמודות לטבלה קיימת ב-SQLite — ALTER TABLE שקט לשדרוגים."""
    engine = get_engine()
    with engine.connect() as conn:
        try:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
            conn.commit()
        except Exception:
            pass  # העמודה כבר קיימת


def init_db():
    from . import models  # noqa: F401 — רישום טבלאות
    Base.metadata.create_all(get_engine())
    _add_column_if_missing("jobs", "lithophane_json", "TEXT")
    _add_column_if_missing("jobs", "text_prompt", "TEXT")


@contextmanager
def db_session() -> Session:
    get_engine()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """Dependency ל-FastAPI."""
    with db_session() as s:
        yield s
