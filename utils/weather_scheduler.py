import asyncio
import logging
from datetime import datetime, time, timedelta
import pytz
from aiogram import Bot
from config import GROUP_CHAT_ID
from database.crud import get_users_with_district
from utils.weather import get_current_weather, get_forecast, clothing_recommendation, get_weather_cached
from utils.districts import DISTRICT_COORDS

logger = logging.getLogger(__name__)

# Московский часовой пояс
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

async def send_weather_to_users(bot: Bot, is_morning: bool):
    try:
        users = get_users_with_notifications_enabled()
        if not users:
            logger.info("Нет пользователей с указанным районом и включёнными уведомлениями")
            return

        for user in users:
            district = user['district']
            weather = await get_weather_cached(district)
            if not weather:
                continue

            if is_morning:
                text = (
                    f"🌅 *Доброе утро, {user['name']}!*\n\n"
                    f"Прогноз погоды в вашем районе ({district}) на сегодня:\n"
                    f"🌡 Сейчас: {weather['temp']}°C (ощущается как {weather['feels_like']}°C)\n"
                    f"💧 Влажность: {weather['humidity']}%\n"
                    f"💨 Ветер: {weather['wind_speed']} м/с\n"
                    f"☁️ {weather['description']}\n\n"
                    f"🧥 {clothing_recommendation(weather['temp'])}\n\n"
                    f"Хороших покатушек! 🏍️"
                )
            else:
                text = (
                    f"🔄 *Обновление погоды, {user['name']}!*\n\n"
                    f"Погода в вашем районе ({district}) сейчас:\n"
                    f"🌡 {weather['temp']}°C (ощущается как {weather['feels_like']}°C)\n"
                    f"💧 Влажность: {weather['humidity']}%\n"
                    f"💨 Ветер: {weather['wind_speed']} м/с\n"
                    f"☁️ {weather['description']}\n\n"
                    f"🧥 {clothing_recommendation(weather['temp'])}"
                )
            try:
                await bot.send_message(user['id'], text, parse_mode="Markdown")
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Не удалось отправить погоду пользователю {user['id']}: {e}")
    except Exception as e:
        logger.error(f"Ошибка в send_weather_to_users: {e}", exc_info=True)

async def weather_scheduler_loop(bot: Bot):
    while True:
        now_moscow = datetime.now(MOSCOW_TZ)
        target_times = [time(7, 30), time(18, 0)]
        for target_time in target_times:
            next_run = datetime.combine(now_moscow.date(), target_time, tzinfo=MOSCOW_TZ)
            if now_moscow.time() >= target_time:
                next_run += timedelta(days=1)
            wait_seconds = (next_run - now_moscow).total_seconds()
            await asyncio.sleep(wait_seconds)
            from utils.weather import _weather_cache
            _weather_cache.clear()
            is_morning = (target_time.hour == 7 and target_time.minute == 30)
            await send_weather_to_group(bot, is_morning=is_morning)
            await send_weather_to_users(bot, is_morning=is_morning)
        await asyncio.sleep(1)

async def send_weather_to_users(bot: Bot, is_morning: bool):
    """Отправляет персонализированную погоду в ЛС."""
    users = get_users_with_notifications_enabled()  # новая функция
    try:
        users = get_users_with_district()
        if not users:
            logger.info("Нет пользователей с указанным районом для рассылки погоды")
            return

        for user in users:
            district = user['district']
            weather = await get_weather_cached(district)
            if not weather:
                continue

            if is_morning:
                text = (
                    f"🌅 *Доброе утро, {user['name']}!*\n\n"
                    f"Прогноз погоды в вашем районе ({district}) на сегодня:\n"
                    f"🌡 Сейчас: {weather['temp']}°C (ощущается как {weather['feels_like']}°C)\n"
                    f"💧 Влажность: {weather['humidity']}%\n"
                    f"💨 Ветер: {weather['wind_speed']} м/с\n"
                    f"☁️ {weather['description']}\n\n"
                    f"🧥 {clothing_recommendation(weather['temp'])}\n\n"
                    f"Хороших покатушек! 🏍️"
                )
            else:
                text = (
                    f"🔄 *Обновление погоды, {user['name']}!*\n\n"
                    f"Погода в вашем районе ({district}) сейчас:\n"
                    f"🌡 {weather['temp']}°C (ощущается как {weather['feels_like']}°C)\n"
                    f"💧 Влажность: {weather['humidity']}%\n"
                    f"💨 Ветер: {weather['wind_speed']} м/с\n"
                    f"☁️ {weather['description']}\n\n"
                    f"🧥 {clothing_recommendation(weather['temp'])}"
                )
            try:
                await bot.send_message(user['id'], text, parse_mode="Markdown")
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Не удалось отправить погоду пользователю {user['id']}: {e}")
    except Exception as e:
        logger.error(f"Ошибка в send_weather_to_users: {e}", exc_info=True)

def get_users_with_notifications_enabled():
    with get_session() as session:
        users = session.query(User).filter(User.district.isnot(None), User.weather_notifications == True).all()
        return [{"id": u.telegram_id, "name": u.name, "district": u.district} for u in users]