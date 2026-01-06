from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db_session() -> Session:
    return SessionLocal()
