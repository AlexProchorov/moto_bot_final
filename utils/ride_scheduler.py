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
    """Закрывает ежедневные темы в 03:00 МСК."""
    while True:
        if is_moscow_time(3, 0):
            with get_session() as session:
                topics = session.query(DailyActiveTopic).all()
                for topic in topics:
                    try:
                        await bot.edit_forum_topic(GROUP_CHAT_ID, topic.message_thread_id, name=f"🚫 Покатушки {topic.date} (завершены)")
                        await bot.close_forum_topic(GROUP_CHAT_ID, topic.message_thread_id)
                        logger.info(f"Closed daily topic {topic.message_thread_id}")
                    except Exception as e:
                        logger.error(f"Failed to close topic {topic.message_thread_id}: {e}")
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
    """Архивирует прошедшие заезды."""
    while True:
        now = datetime.now()
        with get_session() as session:
            rides = session.query(Ride).filter(Ride.is_active == True, Ride.date <= now).all()
            for ride in rides:
                try:
                    if ride.message_thread_id:
                        await bot.edit_forum_topic(GROUP_CHAT_ID, ride.message_thread_id, name=f"📦 Архив: {ride.title}")
                        await bot.close_forum_topic(GROUP_CHAT_ID, ride.message_thread_id)
                except Exception as e:
                    logger.error(f"Ошибка при архивации темы заезда {ride.id}: {e}")
                ride.is_active = False
                session.commit()
                await bot.send_message(GROUP_CHAT_ID, f"🏁 Заезд «{ride.title}» завершён (время прошло). Тема закрыта.")
        await asyncio.sleep(300)