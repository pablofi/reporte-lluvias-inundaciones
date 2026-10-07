from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


url = make_url(get_settings().database_url)
if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if url.get_backend_name() == "sqlite" else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_db():
    with SessionLocal() as session:
        yield session


def sqlite_connection_setup(connection, record):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


def initialize_database(target_engine=engine):
    # Fase 02: esquema aditivo encapsulado; cambios posteriores necesitarán migraciones.
    from app.models import sources  # noqa: F401
    if target_engine.dialect.name == "sqlite" and not event.contains(target_engine, "connect", sqlite_connection_setup):
        event.listen(target_engine, "connect", sqlite_connection_setup)
    Base.metadata.create_all(target_engine)
