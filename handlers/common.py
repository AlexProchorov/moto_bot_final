
from aiogram.filters import Command
from aiogram.types import Message
from database.engine import get_session
from database.models import User
from utils.districts import DISTRICT_COORDS
from database.crud import get_users_by_district
from utils.weather import get_current_weather, get_weather_by_coords, get_weather_cached, clothing_recommendation
from database.crud import update_user_rules_accepted, delete_user_by_id, get_user_by_telegram_id
from config import GROUP_CHAT_ID
from aiogram.types import CallbackQuery
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from messages import welcome_with_rules
import asyncio
from database.crud import get_user_bike_details
from database.crud import update_user_weather_notifications
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот мотосообщества. Используйте /init для начала регистрации (только для админов).")

@router.message(Command("weather_now"))
async def weather_now(message: Message):
    if message.chat.type not in ["private", "group", "supergroup"]:
        await message.answer("Команда доступна в ЛС и группе.")
        return

    user_id = message.from_user.id
    district = None

    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            district = user.district

    text_parts = []

    if district and district in DISTRICT_COORDS:
        coords = DISTRICT_COORDS[district]
        weather = await get_weather_cached(district)
        if weather:
            text_parts.append(
                f"🌤 *Погода в вашем районе ({district}):*\n"
                f"🌡 Температура: {weather['temp']}°C (ощущается как {weather['feels_like']}°C)\n"
                f"💧 Влажность: {weather['humidity']}%\n"
                f"💨 Ветер: {weather['wind_speed']} м/с\n"
                f"☁️ {weather['description']}\n"
                f"🧥 {clothing_recommendation(weather['temp'])}"
            )
        else:
            text_parts.append(f"❌ Не удалось получить погоду для района {district}.")
    elif district:
        text_parts.append(f"❌ Район '{district}' не найден в списке координат.")

    moscow_weather = await get_current_weather()
    if moscow_weather:
        text_parts.append(
            f"🌍 *Погода в Москве:*\n"
            f"🌡 Температура: {moscow_weather['temp']}°C (ощущается как {moscow_weather.get('feels_like', moscow_weather['temp'])}°C)\n"
            f"💧 Влажность: {moscow_weather['humidity']}%\n"
            f"💨 Ветер: {moscow_weather['wind_speed']} м/с\n"
            f"☁️ {moscow_weather['description']}\n"
            f"🧥 {clothing_recommendation(moscow_weather['temp'])}"
        )
    else:
        text_parts.append("❌ Не удалось получить погоду в Москве.")

    if not text_parts:
        await message.answer("❌ Не удалось получить данные о погоде.")
        return

    await message.answer("\n\n".join(text_parts), parse_mode="Markdown")

@router.message(Command("neighbors"))
async def neighbors_cmd(message: Message):
    user_id = message.from_user.id
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await message.answer("❌ Вы не зарегистрированы.")
            return
        district = user.district
        if not district:
            await message.answer("❌ У вас не указан округ. Используйте /edit_my_profile.")
            return

    users = get_users_by_district(district)
    neighbors = [u for u in users if u['id'] != user_id]
    if not neighbors:
        await message.answer(f"👤 Вы единственный участник в округе {district}.", parse_mode="HTML")
        return

    lines = []
    for u in neighbors:
        name = u['name'] or "Участник"
        username = u['username']
        if username:
            lines.append(f"• {name} (@{username})")
        else:
            lines.append(f"• {name}")
    text = f"🏘 <b>В вашем округе {district} проживает {len(neighbors)} участник(а):</b>\n\n" + "\n".join(lines)
    await message.answer(text, parse_mode="HTML")

from database.crud import update_user_rules_accepted, delete_user_by_id, get_user_by_telegram_id
from config import GROUP_CHAT_ID

@router.callback_query(F.data == "rules_accept")
async def rules_accept(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    update_user_rules_accepted(user_id, True)
    await callback.answer("✅ Спасибо! Добро пожаловать в сообщество!")
    await callback.message.delete()
    
    # Получаем данные о мотоцикле (синхронно)
    bike_brand, bike_model = get_user_bike_details(user_id)
    bike_text = ""
    if bike_brand and bike_model:
        bike_text = f"\n🏍 У тебя классный мопед: {bike_brand} {bike_model}"
    
    await callback.message.answer(
        "🎉 Поздравляем с вступлением в наше мотосообщество!\n"
        "Будь на связи, участвуй в покатушках и получай удовольствие! 🏍️"
    )
    
    if GROUP_CHAT_ID:
        try:
            user = await bot.get_chat(user_id)
            name = user.first_name or "Участник"
            username = user.username
            if username:
                mention = f"@{username}"
            else:
                mention = f'<a href="tg://user?id={user_id}">{name}</a>'
            await bot.send_message(
                GROUP_CHAT_ID,
                f"👋 Привет, {mention}! Рады видеть тебя с нами. Добро пожаловать в команду!{bike_text} 🏍️",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить приветствие в группу: {e}")
@router.callback_query(F.data == "rules_decline")
async def rules_decline(callback: CallbackQuery):
    user_id = callback.from_user.id
    # Удаляем профиль пользователя
    delete_user_by_id(user_id)
    await callback.answer("❌ Вы не согласились с правилами.")
    await callback.message.edit_text(
        "Извини, но без согласия с правилами ты не сможешь быть полноценным участником нашей команды.\n"
        "Если передумаешь – зарегистрируйся заново."
    )

@router.message(Command("rules"))
async def cmd_rules(message: Message):
    # Проверяем, зарегистрирован ли пользователь и принял ли правила
    user = get_user_by_telegram_id(message.from_user.id)
    if not user or not user.rules_accepted:
        await message.answer("❌ Вы не зарегистрированы или не приняли правила. Используйте /start для регистрации.")
        return
    await message.answer(rules_message(), parse_mode="Markdown", reply_markup=get_rules_keyboard())


@router.message(Command("weather_settings"))
async def weather_settings_cmd(message: Message):
    user_id = message.from_user.id
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await message.answer("❌ Вы не зарегистрированы.")
            return
        current = user.weather_notifications
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔕 Выключить уведомления" if current else "🔔 Включить уведомления",
            callback_data="weather_toggle"
        )]
    ])
    status = "включены" if current else "выключены"
    await message.answer(f"🌦 Уведомления о погоде {status}. Нажмите кнопку, чтобы изменить:", reply_markup=kb)

@router.callback_query(F.data == "weather_toggle")
async def weather_toggle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            user.weather_notifications = not user.weather_notifications
            session.commit()
            new_status = "включены" if user.weather_notifications else "выключены"
            await callback.message.edit_text(f"✅ Уведомления о погоде {new_status}.")
        else:
            await callback.message.edit_text("❌ Пользователь не найден.")
    await callback.answer()


@router.message(Command("weather_settings"))
async def weather_settings_cmd(message: Message):
    user_id = message.from_user.id
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await message.answer("❌ Вы не зарегистрированы.")
            return
        current = user.weather_notifications
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔕 Выключить уведомления" if current else "🔔 Включить уведомления",
            callback_data="weather_toggle"
        )]
    ])
    status = "включены" if current else "выключены"
    await message.answer(f"🌦 Уведомления о погоде: {status}.\nНажмите кнопку, чтобы изменить:", reply_markup=kb)

@router.callback_query(F.data == "weather_toggle")
async def weather_toggle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            user.weather_notifications = not user.weather_notifications
            session.commit()
            new_status = "включены" if user.weather_notifications else "выключены"
            await callback.message.edit_text(f"✅ Уведомления о погоде {new_status}.")
        else:
            await callback.message.edit_text("❌ Пользователь не найден.")
    await callback.answer()