import re
from aiogram.filters import BaseFilter
from aiogram.types import Message

class BotSpamFilter(BaseFilter):
    """
    Фильтр для удаления любых сообщений, связанных с ботами:
    - отправленные через бота (via_bot)
    - пересланные от бота
    - содержащие упоминания @бот
    """
    async def __call__(self, message: Message):
        # Не трогаем сообщения от самого бота
        if message.from_user.is_bot:
            return False

        # 1. Сообщение отправлено через бота (via @...)
        if message.via_bot is not None:
            return {"bots_mentioned": [f"via @{message.via_bot.username}"]}

        # 2. Сообщение переслано от бота
        if message.forward_from and message.forward_from.is_bot:
            return {"bots_mentioned": [f"forward from @{message.forward_from.username}"]}

        # 3. Текст содержит @имя_бота (например, @PredskazBot)
        text = message.text or message.caption
        if text:
            matches = re.findall(r'@[a-zA-Z][a-zA-Z0-9_]{4,31}bot', text, re.IGNORECASE)
            if matches:
                return {"bots_mentioned": matches}

        return False