# database/engine.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config import DB_URL
from .models import Base
from contextlib import contextmanager

# Синхронный движок (только синхронный)
sync_engine = create_engine(DB_URL, echo=False)
SyncSessionLocal = sessionmaker(bind=sync_engine, class_=Session)

@contextmanager
def get_session():
    """Контекстный менеджер для получения сессии БД."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def init_db():
    Base.metadata.create_all(bind=sync_engine)

def close_db():
    sync_engine.dispose()