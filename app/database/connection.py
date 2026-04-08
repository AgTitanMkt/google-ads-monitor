from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from app.config import get_settings
from app.models.campaign import Base

_engine = None
_SessionLocal = None


def _init():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            pool_size=5,
        )
        Base.metadata.create_all(bind=_engine)
        _SessionLocal = sessionmaker(bind=_engine)


def get_engine():
    _init()
    return _engine


@contextmanager
def get_session() -> Session:
    _init()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
