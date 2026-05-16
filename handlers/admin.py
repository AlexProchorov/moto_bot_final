import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatPermissions
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_IDS, GROUP_CHAT_ID
from database.crud import get_all_users, get_all_birthdays_sorted, get_upcoming_birthdays, set_setting, get_registered_users_count
from database.engine import get_session
from database.models import User
import asyncio
from datetime import datetime, timedelta
import html
from collections import Counter


logger = logging.getLogger(__name__)
router = Router(name="admin")

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

# ---------- Панель администратора ----------
@router.message(Command("admin_panel"))
async def admin_panel_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Инициализировать регистрацию", callback_data="admin:init")],
        [InlineKeyboardButton(text="📋 Список участников", callback_data="admin:participants")],
        [InlineKeyboardButton(text="🎂 Дни рождения (все)", callback_data="admin:bd_all")],
        [InlineKeyboardButton(text="🎂 Ближайшие ДР (30 дней)", callback_data="admin:bd_soon")],
        [InlineKeyboardButton(text="🌦 Включить рассылку погоды", callback_data="admin:weather_on")],
        [InlineKeyboardButton(text="🌦 Отключить рассылку погоды", callback_data="admin:weather_off")],
        [InlineKeyboardButton(text="🔇 Замутить пользователя", callback_data="admin:mute")],
        [InlineKeyboardButton(text="➕ Создать плановый заезд", callback_data="admin:new_ride")],
        [InlineKeyboardButton(text="🏁 Отменить плановый заезд", callback_data="admin:end_ride")],
    ])
    await message.answer("🛠 *Панель администратора*\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")

# ---------- Обработчик кнопок ----------
@router.callback_query(F.data.startswith("admin:"))
async def admin_callback_handler(callback: CallbackQuery):
    await callback.answer()
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.message.answer("⛔ Только для админов.")
        return

    if action == "init":
        me = await callback.bot.get_me()
        url = f"https://t.me/{me.username}?start=register"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Зарегистрироваться", url=url)]
        ])
        await callback.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=("🏍 Добро пожаловать в моточат!\n\n"
                  "Чтобы зарегистрироваться, нажмите кнопку ниже — бот откроется в личке."),
            reply_markup=kb,
        )
        await callback.message.answer("✅ Кнопка регистрации отправлена в группу.")
        logger.info("Admin %s sent init message to group", user_id)

    elif action == "participants":
        await show_participants_panel(callback.message)
    elif action == "stats_bikes":
        await stats_bikes_callback(callback)
    elif action == "detailed_list":
        await detailed_list_callback(callback)


    elif action == "bd_all":
        birthdays = get_all_birthdays_sorted()
        if not birthdays:
            await callback.message.answer("📭 В базе нет данных о днях рождения.")
            return
        response = "🎂 Дни рождения участников:\n\n"
        for b in birthdays:
            response += f"• {b['name']} (@{b['username'] or 'нет юзернейма'}) — {b['birthday']}\n"
        await callback.message.answer(response)

    elif action == "bd_soon":
        upcoming = get_upcoming_birthdays(days=30)
        if not upcoming:
            await callback.message.answer("🎉 Ближайших дней рождения в течение 30 дней нет.")
            return
        response = "🎂 Ближайшие дни рождения (в течение 30 дней):\n\n"
        for b in upcoming:
            response += f"• {b['name']} (@{b['username'] or 'нет юзернейма'}) — {b['birthday']} (через {b['days_left']} дн.)\n"
        await callback.message.answer(response)

    elif action == "weather_on":
        set_setting("weather_broadcast_enabled", "true")
        await callback.message.answer("✅ Рассылка прогноза погоды включена.")

    elif action == "weather_off":
        set_setting("weather_broadcast_enabled", "false")
        await callback.message.answer("❌ Рассылка прогноза погоды выключена.")

    elif action == "mute":
        await callback.message.answer("Используйте команду /mute_user в ЛС.")

    elif action == "new_ride":
        await callback.message.answer(
            "Для создания планового заезда используйте команду `/new_ride` в ЛС.\n"
            "Бот попросит ввести название, дату, время, место и описание."
        )
    elif action == "end_ride":
        await callback.message.answer(
            "Для отмены планового заезда используйте команду `/end_ride <id_заезда>` в ЛС.\n"
            "ID заезда можно узнать командой `/rides`."
        )
    else:
        await callback.message.answer("Неизвестное действие.")

# ---------- Остальные админ-команды (init, participants_info, bd_info, weather_on/off, mute_user, get_user_id) ----------
# Они уже есть в вашем файле, я их не удаляю. Просто убедитесь, что они не дублируются.

async def show_participants_panel(message: Message):
    # 1. Количество зарегистрированных в боте
    from database.crud import get_registered_users_count
    registered_count = get_registered_users_count()
    # 2. Общее количество участников в группе
    try:
        total_users = await message.bot.get_chat_member_count(GROUP_CHAT_ID)
    except Exception as e:
        total_users = "неизвестно"
        logger.error(f"Ошибка получения количества участников группы: {e}")

    # Клавиатура
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика по мотоциклам", callback_data="admin:stats_bikes")],
        [InlineKeyboardButton(text="📋 Подробный список участников", callback_data="admin:detailed_list")],
    ])
    await message.answer(
        f"👥 *Статистика сообщества*\n\n"
        f"📌 Зарегистрировано в боте: `{registered_count}`\n"
        f"📌 Всего участников в группе: `{total_users}`\n\n"
        f"Выберите дополнительную информацию:",
        reply_markup=kb,
        parse_mode="Markdown"
    )



async def stats_bikes_callback(callback: CallbackQuery):
    """Выводит статистику по маркам и моделям мотоциклов."""
    try:
        users = get_all_users()
        bike_counter = Counter()
        model_counter = Counter()
        total_with_bike = 0

        for user in users:
            bike = user.get('bike', '')
            if bike and bike.strip():
                total_with_bike += 1
                parts = bike.split(maxsplit=1)
                brand = parts[0] if parts else "Неизвестно"
                model = parts[1] if len(parts) > 1 else ""
                bike_counter[brand] += 1
                if model:
                    model_counter[(brand, model)] += 1

        if not bike_counter:
            await callback.message.answer("📊 Нет данных о мотоциклах среди зарегистрированных.")
            return

        text = "<b>📊 Статистика по мотоциклам</b>\n\n"
        text += f"👥 Всего зарегистрировано: {len(users)}\n"
        text += f"🏍 Указали мотоцикл: {total_with_bike}\n\n"
        text += "<b>Марки:</b>\n"
        for brand, count in bike_counter.most_common():
            text += f"• {html.escape(brand)}: {count}\n"
        text += "\n<b>Модели (топ-10):</b>\n"
        for (brand, model), count in model_counter.most_common(10):
            text += f"• {html.escape(brand)} {html.escape(model)}: {count}\n"

        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                await callback.message.answer(text[i:i+4000], parse_mode="HTML")
        else:
            await callback.message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в stats_bikes_callback: {e}")
        await callback.message.answer("❌ Не удалось получить статистику.")

async def detailed_list_callback(callback: CallbackQuery):
    """Выводит подробный список участников."""
    try:
        users = get_all_users()
        if not users:
            await callback.message.answer("📭 Нет зарегистрированных участников.")
            return

        # Получаем округа для всех пользователей
        from database.engine import get_session
        from database.models import User
        district_map = {}
        with get_session() as session:
            for u in session.query(User.telegram_id, User.district).all():
                district_map[u.telegram_id] = u.district or "не указан"

        text = "<b>📋 Подробный список участников:</b>\n\n"
        for user in users:
            name = html.escape(user['name'] or "Без имени")
            username = user['username']
            uid = user['id']
            bike = html.escape(user.get('bike', 'не указан'))
            district = html.escape(district_map.get(uid, "не указан"))

            if username:
                mention = f"@{html.escape(username)}"
            else:
                mention = f'<a href="tg://user?id={uid}">{name}</a>'

            text += f"• {mention} — {bike} — {district}\n"
            if len(text) > 3800:   # оставляем запас для сообщения
                await callback.message.answer(text, parse_mode="HTML")
                text = ""

        if text:
            await callback.message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в detailed_list_callback: {e}")
        await callback.message.answer("❌ Не удалось получить список участников.")
