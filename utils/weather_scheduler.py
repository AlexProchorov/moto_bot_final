import asyncio
import logging
from datetime import datetime, time
from aiogram import Bot
from config import GROUP_CHAT_ID
from database.crud import get_setting
from utils.weather import get_current_weather, get_forecast, clothing_recommendation

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения последнего отправленного прогноза (в течение дня)
last_sent_forecast = None

async def send_weather_alert(bot: Bot, forecast_data, is_morning=False):
    """Отправляет сообщение с погодой в группу."""
    if is_morning:
        text = (
            f"🌅 *Доброе утро, мотосообщество!*\n\n"
            f"Прогноз погоды на сегодня:\n"
            f"🌡 Температура: от {forecast_data['temp_min']}°C до {forecast_data['temp_max']}°C\n"
            f"💧 Влажность: {forecast_data.get('humidity', '?')}%\n"
            f"💨 Ветер: {forecast_data.get('wind_speed', '?')} м/с\n"
            f"☁️ {forecast_data['description']}\n\n"
            f"🧥 *Рекомендация:* {clothing_recommendation(forecast_data.get('temp', forecast_data['temp_min']))}"
        )
    else:
        text = (
            f"🔄 *Обновление погоды:*\n"
            f"🌡 Сейчас: {forecast_data['temp']}°C\n"
            f"💨 Ветер: {forecast_data['wind_speed']} м/с\n"
            f"💧 Влажность: {forecast_data['humidity']}%\n"
            f"☁️ {forecast_data['description']}\n\n"
            f"🧥 {clothing_recommendation(forecast_data['temp'])}"
        )
    await bot.send_message(GROUP_CHAT_ID, text, parse_mode="Markdown")

async def morning_weather_task(bot: Bot):
    """Задача для 07:00 – прогноз на день."""
    enabled = get_setting("weather_broadcast_enabled", "false") == "true"
    if not enabled:
        logger.info("Morning weather broadcast disabled.")
        return
    forecast = await get_forecast()
    if forecast:
        # добавим влажность и ветер из текущей погоды для полноты
        current = await get_current_weather()
        if current:
            forecast['humidity'] = current['humidity']
            forecast['wind_speed'] = current['wind_speed']
        await send_weather_alert(bot, forecast, is_morning=True)
        # обновляем last_sent_forecast, чтобы днём сравнивать
        global last_sent_forecast
        last_sent_forecast = current  # сохраняем текущие показатели
    else:
        logger.error("Morning forecast not available")

async def periodic_weather_task(bot: Bot):
    """Задача для 10,15,20 часов – обновление погоды, если изменилась."""
    enabled = get_setting("weather_broadcast_enabled", "false") == "true"
    if not enabled:
        logger.info("Periodic weather broadcast disabled.")
        return
    current = await get_current_weather()
    if not current:
        return
    global last_sent_forecast
    # Сравниваем с последним отправленным (с учётом округления до целых)
    if (last_sent_forecast is None or
        abs(current['temp'] - last_sent_forecast['temp']) >= 2 or
        current['description'] != last_sent_forecast['description']):
        await send_weather_alert(bot, current, is_morning=False)
        last_sent_forecast = current
    else:
        logger.info("Weather unchanged, no update sent.")

async def weather_scheduler_loop(bot: Bot):
    """Главный цикл, проверяющий время и запускающий задачи."""
    while True:
        now = datetime.now()
        # Утренняя задача – в 07:00
        if now.hour == 7 and now.minute == 0:
            await morning_weather_task(bot)
            await asyncio.sleep(60)  # чтобы не сработало повторно в ту же минуту
        # Периодические задачи – в 10:00, 15:00, 20:00
        if now.hour in [10, 15, 20] and now.minute == 0:
            await periodic_weather_task(bot)
            await asyncio.sleep(60)
        await asyncio.sleep(30)  # проверяем каждые 30 секунд