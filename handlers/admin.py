import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton  # добавлено
from config import ADMIN_IDS, GROUP_CHAT_ID
from database.crud import get_all_users, get_all_birthdays_sorted, get_upcoming_birthdays
from database.models import User
from database.crud import get_all_users, get_all_birthdays_sorted, get_upcoming_birthdays, set_setting

logger = logging.getLogger(__name__)
router = Router(name="admin")

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ========== СУЩЕСТВУЮЩАЯ КОМАНДА /init ==========
@router.message(Command("init"))
async def init_cmd(message: Message):
    if message.chat.type != "private":
        await message.answer("Команду /init используйте в личных сообщениях с ботом.")
        return
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    if not GROUP_CHAT_ID:
        await message.answer("❌ GROUP_CHAT_ID не задан в .env")
        return

    me = await message.bot.get_me()
    url = f"https://t.me/{me.username}?start=register"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Зарегистрироваться", url=url)]
    ])
    await message.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=("🏍 Добро пожаловать в моточат!\n\n"
              "Чтобы зарегистрироваться, нажмите кнопку ниже — бот откроется в личке."),
        reply_markup=kb,
    )
    await message.answer("✅ Кнопка регистрации отправлена в группу.")
    logger.info("Admin %s sent init message to group", message.from_user.id)


@router.message(Command("participants_info"))
async def participants_info(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    users = get_all_users()
    if not users:
        await message.answer("📭 Пока нет зарегистрированных участников.")
        return

    response = "📋 Список участников:\n\n"
    for u in users:
        response += f"• {u['name']} (@{u['username'] or 'нет юзернейма'})\n"
        response += f"  🏍 {u['bike']}\n"
    await message.answer(response)   # parse_mode удалён

@router.message(Command("bd_info"))
async def bd_info(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    birthdays = get_all_birthdays_sorted()
    if not birthdays:
        await message.answer("📭 В базе нет данных о днях рождения.")
        return

    response = "🎂 Дни рождения участников:\n\n"
    for b in birthdays:
        response += f"• {b['name']} (@{b['username'] or 'нет юзернейма'}) — {b['birthday']}\n"
    await message.answer(response)

@router.message(Command("bd_info_soon"))
async def bd_info_soon(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    upcoming = get_upcoming_birthdays(days=30)
    if not upcoming:
        await message.answer("🎉 Ближайших дней рождения в течение 30 дней нет.")
        return

    response = "🎂 Ближайшие дни рождения (в течение 30 дней):\n\n"
    for b in upcoming:
        response += f"• {b['name']} (@{b['username'] or 'нет юзернейма'}) — {b['birthday']} (через {b['days_left']} дн.)\n"
    await message.answer(response)


@router.message(Command("weather_on"))
async def weather_on(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    set_setting("weather_broadcast_enabled", "true")
    await message.answer("✅ Рассылка прогноза погоды включена.")

@router.message(Command("weather_off"))
async def weather_off(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    set_setting("weather_broadcast_enabled", "false")
    await message.answer("❌ Рассылка прогноза погоды выключена.")