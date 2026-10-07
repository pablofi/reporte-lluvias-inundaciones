from pathlib import Path

from sqlalchemy import create_engine
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
