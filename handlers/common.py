from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from database.engine import get_session
from database.models import User
from utils.districts import DISTRICT_COORDS
from database.crud import get_users_by_district
from utils.weather import get_current_weather, get_weather_by_coords, get_weather_cached, clothing_recommendation


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
