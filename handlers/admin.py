import logging
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton  # добавлено
from config import ADMIN_IDS, GROUP_CHAT_ID
from database.crud import get_all_users, get_all_birthdays_sorted, get_upcoming_birthdays
from database.models import User
from database.crud import get_all_users, get_all_birthdays_sorted, get_upcoming_birthdays, set_setting
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ChatMember, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatPermissions
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
from database.crud import get_all_users, get_all_birthdays_sorted, get_upcoming_birthdays, set_setting, get_users_by_district
from datetime import datetime, timedelta

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



# FSM для бана
class MuteStates(StatesGroup):
    waiting_user_input = State()
    waiting_duration = State()


@router.message(Command("mute_user"))
async def mute_user_cmd(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    if message.chat.type != "private":
        await message.answer("Команда доступна только в ЛС.")
        return
    await message.answer("Введите числовой ID пользователя (можно получить через @userinfobot или ответом на сообщение командой /get_user_id):")
    await state.set_state(MuteStates.waiting_user_input)
    await state.update_data(chat_id=GROUP_CHAT_ID)

@router.message(MuteStates.waiting_user_input)
async def mute_user_input(message: Message, state: FSMContext):
    user_input = message.text.strip()
    if not user_input.isdigit():
        await message.answer("❌ Введите числовой ID.")
        return
    user_id = int(user_input)
    try:
        member = await message.bot.get_chat_member(GROUP_CHAT_ID, user_id)
        user_name = member.user.full_name or member.user.first_name
    except Exception:
        await message.answer(f"❌ Пользователь с ID {user_id} не найден в группе.")
        await state.clear()
        return
    await state.update_data(target_user_id=user_id, target_user_name=user_name)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 минут", callback_data="mute_duration:5")],
        [InlineKeyboardButton(text="30 минут", callback_data="mute_duration:30")],
        [InlineKeyboardButton(text="60 минут", callback_data="mute_duration:60")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="mute_cancel")]
    ])
    await message.answer(f"Выбран пользователь: {user_name}. Выберите время мута:", reply_markup=kb)
    await state.set_state(MuteStates.waiting_duration)

@router.callback_query(MuteStates.waiting_duration, F.data.startswith("mute_duration:"))
async def mute_duration_selected(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    duration = int(callback.data.split(":")[1])
    data = await state.get_data()
    user_id = data['target_user_id']
    user_name = data['target_user_name']
    chat_id = data['chat_id']

    # Проверка прав бота
    bot_member = await bot.get_chat_member(chat_id, bot.id)
    if not bot_member.can_restrict_members:
        await callback.message.edit_text(
            "❌ У бота нет права 'Блокировка пользователей'.\n\n"
            "Выдайте это право в настройках группы, затем перезапустите бота командой:\n"
            "`systemctl restart motobot`"
        )
        await state.clear()
        return

    until_date = datetime.now() + timedelta(minutes=duration)
    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )

    try:
        await bot.restrict_chat_member(chat_id, user_id, permissions=permissions, until_date=until_date)
    except Exception as e:
        logger.error(f"Mute error: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {e}")
        await state.clear()
        return

    # Креативное сообщение
    if duration == 5:
        msg = f"🔇 {user_name}, остынь! Мут на 5 минут."
    elif duration == 30:
        msg = f"🤫 {user_name}, охладись! Мут на 30 минут."
    else:
        msg = f"🔕 {user_name}, замёрзни! Мут на 60 минут."
    await bot.send_message(chat_id, msg)

    # Планируем снятие мута
    async def unmute():
        await asyncio.sleep(duration * 60)
        try:
            permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            await bot.restrict_chat_member(chat_id, user_id, permissions=permissions)
            await bot.send_message(chat_id, f"✅ {user_name} может снова писать.")
        except Exception as e:
            logger.error(f"Unmute error: {e}")

    asyncio.create_task(unmute())

    await callback.message.edit_text(f"✅ Пользователю {user_name} запрещено писать на {duration} минут.")
    await state.clear()

@router.callback_query(F.data == "mute_cancel")
async def mute_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("❌ Операция отменена.")
    await state.clear()

@router.message(Command("get_user_id"))
async def get_user_id_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    if not message.reply_to_message:
        await message.answer("Ответьте на сообщение пользователя, чей ID хотите узнать.")
        return
    user_id = message.reply_to_message.from_user.id
    await message.answer(f"ID пользователя: `{user_id}`", parse_mode="Markdown")


