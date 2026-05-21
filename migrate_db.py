import sys
import logging
from database.engine import engine, get_session
from database.models import Base
from sqlalchemy import inspect, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def drop_wash_tables():
    """Удаляет таблицы, связанные с мойкой, если они существуют."""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS wash_workers"))
        conn.execute(text("DROP TABLE IF EXISTS work_schedule"))
        conn.execute(text("DROP TABLE IF EXISTS wash_subtypes"))
        conn.execute(text("DROP TABLE IF EXISTS wash_service"))
        conn.commit()
        logger.info("Старые таблицы мойки удалены")

def create_missing_columns():
    """Добавляет недостающие колонки в существующие таблицы (например, в users)."""
    inspector = inspect(engine)
    with get_session() as session:
        # Пример для таблицы users: проверим наличие колонки weather_notifications (она должна быть)
        if 'users' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('users')]
            if 'weather_notifications' not in columns:
                session.execute(text("ALTER TABLE users ADD COLUMN weather_notifications BOOLEAN DEFAULT 0"))
                logger.info("Добавлена колонка weather_notifications в users")
            if 'rules_accepted' not in columns:
                session.execute(text("ALTER TABLE users ADD COLUMN rules_accepted BOOLEAN DEFAULT 0"))
                logger.info("Добавлена колонка rules_accepted в users")
            # Добавьте другие необходимые колонки по мере необходимости
        session.commit()

def main():
    logger.info("Запуск миграции базы данных...")
    drop_wash_tables()
    # Создаём все таблицы заново (включая новые таблицы мойки)
    Base.metadata.create_all(bind=engine)
    logger.info("Таблицы созданы (или уже существуют)")
    create_missing_columns()
    logger.info("Миграция завершена успешно")

if __name__ == "__main__":
    main()