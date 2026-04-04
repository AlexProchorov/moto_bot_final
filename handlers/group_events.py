import logging
from aiogram import Router, F
from aiogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError
from database.crud import user_exists
from config import GROUP_CHAT_ID

logger = logging.getLogger(__name__)
router = Router(name="group_events")

@router.chat_member()
async def on_user_joined(event: ChatMemberUpdated):
    # Проверяем, что событие в нужной группе
    if event.chat.id != GROUP_CHAT_ID:
        return

    # Проверяем, что пользователь действительно присоединился (статус был left/kicked → стал member)
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    if not (old_status in ["left", "kicked"] and new_status == "member"):
        return

    user = event.new_chat_member.user
    user_id = user.id
    username = user.username or user.first_name
    mention = f"<a href='tg://user?id={user_id}'>{username}</a>"

    # Проверяем, зарегистрирован ли пользователь
    is_registered = user_exists(user_id)

    # Кнопка-ссылка на бота для регистрации
    me = await event.bot.get_me()
    bot_username = me.username
    register_url = f"https://t.me/{bot_username}?start=register"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Зарегистрироваться в ЛС", url=register_url)]
    ])

    if is_registered:
        text = f"👋 Добро пожаловать, {mention}! ✅ Ты уже зарегистрирован в нашем сообществе."
        # Можно без кнопки, или с кнопкой "Моя анкета" — на ваше усмотрение
        await event.bot.send_message(
            chat_id=event.chat.id,
            text=text,
            parse_mode="HTML"
        )
    else:
        text = (
            f"👋 Привет, {mention}! Ты добавился в нашу мото-группу.\n\n"
            f"📝 Пожалуйста, зарегистрируйся, нажав на кнопку ниже — бот откроется в личном чате."
        )
        await event.bot.send_message(
            chat_id=event.chat.id,
            text=text,
            reply_markup=kb,
            parse_mode="HTML"
        )

    logger.info(f"Приветствие отправлено в группу для {username} (ID: {user_id})")