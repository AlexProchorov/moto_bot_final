from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from utils.weather import get_current_weather, clothing_recommendation

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот мотосообщества. Используйте /init для начала регистрации (только для админов).")


@router.message(Command("weather_now"))
async def weather_now(message: Message):
    if message.chat.type not in ["private", "group", "supergroup"]:
        await message.answer("Команда доступна в ЛС и группе.")
        return
    weather = await get_current_weather()
    if not weather:
        await message.answer("❌ Не удалось получить данные о погоде. Попробуйте позже.")
        return
    text = (
        f"🌤 *Погода сейчас:*\n"
        f"🌡 Температура: {weather['temp']}°C\n"
        f"💧 Влажность: {weather['humidity']}%\n"
        f"💨 Ветер: {weather['wind_speed']} м/с\n"
        f"☁️ {weather['description']}\n\n"
        f"🧥 {clothing_recommendation(weather['temp'])}"
    )
    await message.answer(text, parse_mode="Markdown")