import asyncio
import logging
import random
from datetime import datetime, time, timedelta
from aiogram import Bot
from database.crud import get_today_birthdays
from config import GROUP_CHAT_ID

logger = logging.getLogger(__name__)

BIRTHDAY_TEMPLATES = [
    "{name}, 🎉 С днём рождения! Желаем, чтобы бензин всегда был дешёвым, а дороги — ровными! 🏍💨",
    "{name}, 🥳 Поздравляем! Пусть твой мот никогда не ломается, а газ в ручке всегда приносит улыбку! 🎂",
    "{name}, 🎂 С днюхой! Желаем, чтобы копейки на бензин никогда не заканчивались, а попутчики не жадничали! 😄",
    "{name}, 🏍 Поздравляем! Пусть твой байк будет быстрее ветра, а ты всегда возвращайся домой с улыбкой! 🎁",
    "{name}, 🎈 С днём варенья! Пусть все светофоры горят зелёным, а гаишники машут рукой! 🚦",
    "{name}, 🤣 Поздравляем! Желаем, чтобы мотоцикл слушался, а жена (муж) не ругалась за лишний километр! 🛵",
    "{name}, 🎊 Happy birthday! Пусть подвеска не пробивается, а тормоза не подводят! 💪",
    "{name}, 🎉 Твой день! Желаем море адреналина, океан позитива и ни одного прокола колеса! 🎂",
    "{name}, 🥳 С днюхой! Пусть бак всегда полон, а мозги — трезвы! 😎",
    "{name}, 🎂 Поздравляем! Желаем, чтобы каждый поворот приносил удовольствие, а каждый километр — радость! 🏍"
]

async def birthday_checker(bot: Bot):
    """Проверяет именинников каждый день в 07:00 утра."""
    while True:
        now = datetime.now()
        target_time = time(7, 0)
        next_run = datetime.combine(now.date(), target_time)
        if now.time() >= target_time:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        logger.info("Запуск проверки дней рождения...")
        birthdays = get_today_birthdays()
        if birthdays:
            for user in birthdays:
                name = user.get('name') or 'Участник'
                username = user.get('username')
                display_name = f"{name} (@{username})" if username else name
                template = random.choice(BIRTHDAY_TEMPLATES)
                text = template.format(name=display_name)
                try:
                    await bot.send_message(GROUP_CHAT_ID, text)
                    await bot.send_message(user['id'], f"🎁 Личное поздравление! {text}")
                    logger.info(f"Поздравление отправлено: {display_name}")
                except Exception as e:
                    logger.error(f"Ошибка: {e}")
        else:
            logger.info("Именинников сегодня нет.")

def start_scheduler(bot: Bot):
    loop = asyncio.get_event_loop()
    loop.create_task(birthday_checker(bot))
