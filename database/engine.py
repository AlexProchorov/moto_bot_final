from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config import DB_URL
from .models import Base
from contextlib import contextmanager

# Синхронный движок
engine = create_engine(DB_URL, echo=False)

# Фабрика сессий с отключением expire_on_commit
SyncSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

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
    Base.metadata.create_all(bind=engine)

def close_db():
    engine.dispose()