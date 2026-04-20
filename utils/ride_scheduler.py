import asyncio
import logging
from datetime import datetime, time, timedelta
from aiogram import Bot
from config import GROUP_CHAT_ID
from database.engine import get_session
from database.models import User, Ride, DailyActiveTopic

logger = logging.getLogger(__name__)

# Московское время (UTC+3)
def is_moscow_time(hour: int, minute: int = 0) -> bool:
    now = datetime.utcnow() + timedelta(hours=3)  # UTC+3
    return now.hour == hour and now.minute == minute

async def cleanup_daily_topics(bot: Bot):
    """Удаляет ежедневные темы в 03:00 МСК (полностью удаляет)."""
    while True:
        if is_moscow_time(3, 0):
            with get_session() as session:
                topics = session.query(DailyActiveTopic).all()
                for topic in topics:
                    try:
                        await bot.delete_forum_topic(GROUP_CHAT_ID, topic.message_thread_id)
                        logger.info(f"Deleted daily topic {topic.message_thread_id}")
                    except Exception as e:
                        logger.error(f"Failed to delete topic {topic.message_thread_id}: {e}")
                    session.delete(topic)
                session.commit()
            await asyncio.sleep(60)  # чтобы не сработало повторно
        await asyncio.sleep(30)

async def check_expired_active_users(bot: Bot):
    """Очищает истекшие активные статусы (но не закрывает темы, это делает cleanup_daily_topics)."""
    while True:
        now = datetime.now()
        with get_session() as session:
            users = session.query(User).filter(User.active_until <= now, User.active_until.isnot(None)).all()
            for user in users:
                user.active_until = None
                user.active_topic_id = None
                session.commit()
                logger.info(f"User {user.telegram_id} active status expired.")
        await asyncio.sleep(60)

async def check_expired_rides(bot: Bot):
    """Удаляет темы прошедших заездов в 03:00 МСК."""
    while True:
        if is_moscow_time(3, 0):
            with get_session() as session:
                rides = session.query(Ride).filter(Ride.is_active == True, Ride.date <= datetime.now()).all()
                for ride in rides:
                    try:
                        if ride.message_thread_id:
                            await bot.delete_forum_topic(GROUP_CHAT_ID, ride.message_thread_id)
                            logger.info(f"Удалена тема заезда {ride.id} ({ride.title})")
                    except Exception as e:
                        logger.error(f"Ошибка удаления темы заезда {ride.id}: {e}")
                    ride.is_active = False
                    session.commit()
            await asyncio.sleep(60)  # чтобы не повторять
        await asyncio.sleep(30)