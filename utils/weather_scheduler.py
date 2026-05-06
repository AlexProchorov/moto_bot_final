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

async def send_weather_to_group(bot: Bot, is_morning: bool):
    """Отправляет прогноз погоды по Москве в группу."""
    try:
        if is_morning:
            forecast = await get_forecast()
            if not forecast:
                logger.error("Не удалось получить прогноз для группы")
                return
            text = (
                f"🌅 *Доброе утро, мотосообщество!*\n\n"
                f"Прогноз погоды в Москве на сегодня:\n"
                f"🌡 Температура: от {forecast['temp_min']}°C до {forecast['temp_max']}°C\n"
                f"☁️ {forecast['description']}\n\n"
                f"🧥 *Рекомендация:* {clothing_recommendation(forecast['temp_min'])}"
            )
        else:
            current = await get_current_weather()
            if not current:
                logger.error("Не удалось получить текущую погоду для группы")
                return
            text = (
                f"🔄 *Обновление погоды в Москве:*\n"
                f"🌡 Сейчас: {current['temp']}°C (ощущается как {current.get('feels_like', current['temp'])}°C)\n"
                f"💧 Влажность: {current['humidity']}%\n"
                f"💨 Ветер: {current['wind_speed']} м/с\n"
                f"☁️ {current['description']}\n\n"
                f"🧥 {clothing_recommendation(current['temp'])}"
            )
        await bot.send_message(GROUP_CHAT_ID, text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка в send_weather_to_group: {e}", exc_info=True)

async def send_weather_to_users(bot: Bot, is_morning: bool):
    """Отправляет персонализированную погоду в ЛС."""
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

async def weather_scheduler_loop(bot: Bot):
    """Главный цикл: отправляет погоду в 07:00 и 18:00 по московскому времени."""
    while True:
        now_moscow = datetime.now(MOSCOW_TZ)
        target_times = [time(7, 0), time(18, 0)]
        for target_time in target_times:
            next_run = datetime.combine(now_moscow.date(), target_time, tzinfo=MOSCOW_TZ)
            if now_moscow.time() >= target_time:
                next_run += timedelta(days=1)
            wait_seconds = (next_run - now_moscow).total_seconds()
            await asyncio.sleep(wait_seconds)
            # Перед рассылкой обновляем кеш (очищаем, чтобы получить свежие данные)
            from utils.weather import _weather_cache
            _weather_cache.clear()
            await send_weather_to_group(bot, is_morning=(target_time.hour == 7))
            await send_weather_to_users(bot, is_morning=(target_time.hour == 7))
        await asyncio.sleep(1)  # небольшая пауза после 18:00
