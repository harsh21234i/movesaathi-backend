from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base


def _build_engine():
    connect_args: dict[str, object] = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        settings.DATABASE_URL,
        future=True,
        pool_pre_ping=not settings.DATABASE_URL.startswith("sqlite"),
        echo=settings.SQL_ECHO,
        connect_args=connect_args,
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def create_db_and_tables() -> None:
    Base.metadata.create_all(bind=engine)


def initialize_database() -> None:
    if settings.should_create_tables:
        create_db_and_tables()
