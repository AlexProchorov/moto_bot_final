from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from config import ADMIN_IDS

class AdminCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            if event.text and event.text.startswith('/'):
                command = event.text.split()[0].lower()
                if command in ['/init', '/participants_info', '/bd_info', '/bd_info_soon']:
                    if event.from_user.id not in ADMIN_IDS:
                        await event.answer("⛔ У вас нет прав для выполнения этой команды.")
                        return
        return await handler(event, data)
