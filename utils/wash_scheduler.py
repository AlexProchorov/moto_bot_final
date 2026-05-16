import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from database.engine import get_session
from database.models import WashSlot
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

async def check_wash_reminders(bot: Bot):
    """Каждые 30 минут проверяет, не наступило ли время напоминания о визите (через час после мойки)"""
    while True:
        now = datetime.now()
        # Ищем слоты, где время окончания слота между now-1 час и now, и ещё не отправлено напоминание
        threshold_start = now - timedelta(hours=1)
        with get_session() as session:
            slots = session.query(WashSlot).filter(
                WashSlot.status == 'confirmed',
                WashSlot.confirmation_sent == False
            ).all()
            for slot in slots:
                slot_datetime = datetime.strptime(f"{slot.date} {slot.end_time}", "%Y-%m-%d %H:%M")
                if threshold_start <= slot_datetime <= now:
                    try:
                        await bot.send_message(slot.booked_by, "🔄 Подтвердите, пожалуйста, что визит состоялся. Напишите «+» или «-».")
                        slot.confirmation_sent = True
                        session.commit()
                    except Exception as e:
                        logger.error(f"Ошибка отправки напоминания: {e}")
        await asyncio.sleep(1800)  # 30 минут
