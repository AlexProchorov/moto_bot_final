import logging
from aiogram import Router
from aiogram.types import Message
from filters.bot_spam_filter import BotSpamFilter

logger = logging.getLogger(__name__)
router = Router(name="spam_handlers")

@router.message(BotSpamFilter())
async def delete_bot_spam(message: Message, bots_mentioned: list):
    try:
        await message.delete()
        logger.info(f"[УДАЛЕНО] Сообщение от {message.from_user.id} (@{message.from_user.username}) | Причина: {', '.join(bots_mentioned)}")
    except Exception as e:
        logger.error(f"[ОШИБКА] Не удалось удалить сообщение {message.message_id}: {e}")