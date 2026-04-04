import asyncio
import logging
import random
from datetime import datetime, time
from aiogram import Bot
from database.crud import get_today_birthdays  # напишем эту функцию
from config import GROUP_CHAT_ID

logger = logging.getLogger(__name__)

# Список смешных шаблонов поздравлений
BIRTHDAY_TEMPLATES = [
    "🎉 С днём рождения, {name}! Желаем, чтобы бензин всегда был дешёвым, а дороги — ровными! 🏍💨",
    "🥳 Поздравляем! Пусть твой мот никогда не ломается, а газ в ручке всегда приносит улыбку! 🎂",
    "🎂 С днюхой! Желаем, чтобы копейки на бензин никогда не заканчивались, а попутчики не жадничали! 😄",
    "🏍 Поздравляем! Пусть твой байк будет быстрее ветра, а ты всегда возвращайся домой с улыбкой! 🎁",
    "🎈 С днём варенья! Пусть все светофоры горят зелёным, а гаишники машут рукой! 🚦",
    "🤣 Поздравляем! Желаем, чтобы мотоцикл слушался, а жена (муж) не ругалась за лишний километр! 🛵",
    "🎊 Happy birthday! Пусть подвеска не пробивается, а тормоза не подводят! 💪",
    "🎉 Твой день! Желаем море адреналина, океан позитива и ни одного прокола колеса! 🎂",
    "🥳 С днюхой! Пусть бак всегда полон, а мозги — трезвы! 😎",
    "🎂 Поздравляем! Желаем, чтобы каждый поворот приносил удовольствие, а каждый километр — радость! 🏍"
]

async def birthday_checker(bot: Bot):
    """Фоновая задача: каждый день в 07:00 проверяет именинников и поздравляет."""
    while True:
        now = datetime.now()
        target_time = time(7, 0)
        current_time = now.time()
        # Если сейчас 07:00 (проверяем с точностью до минуты)
        if current_time.hour == target_time.hour and current_time.minute == target_time.minute:
            logger.info("Запуск проверки дней рождения...")
            birthdays = get_today_birthdays()
            if birthdays:
                for user in birthdays:
                    # Выбираем случайный шаблон
                    template = random.choice(BIRTHDAY_TEMPLATES)
                    text = template.format(name=user['name'])
                    try:
                        # Поздравляем в группу
                        await bot.send_message(GROUP_CHAT_ID, text)
                        # Также можно отправить в ЛС, но по желанию
                        await bot.send_message(user['id'], f"🎁 Личное поздравление! {text}")
                        logger.info(f"Поздравление отправлено {user['name']} (id={user['id']})")
                    except Exception as e:
                        logger.error(f"Не удалось поздравить {user['name']}: {e}")
            else:
                logger.info("Именинников сегодня нет.")
            # Ждём сутки, чтобы не спамить
            await asyncio.sleep(86400)
        else:
            # Ждём 60 секунд и проверяем снова
            await asyncio.sleep(60)

def start_scheduler(bot: Bot):
    """Запускает фоновую задачу."""
    loop = asyncio.get_event_loop()
    loop.create_task(birthday_checker(bot))