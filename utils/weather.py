import aiohttp
import logging
from datetime import datetime
from config import WEATHER_API_KEY, WEATHER_CITY

logger = logging.getLogger(__name__)

async def get_current_weather():
    """Возвращает словарь с текущей погодой."""
    url = f"http://api.openweathermap.org/data/2.5/weather?q={WEATHER_CITY}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error(f"Weather API error: {data}")
                    return None
                temp = data['main']['temp']
                temp_min = data['main']['temp_min']
                temp_max = data['main']['temp_max']
                humidity = data['main']['humidity']
                wind_speed = data['wind']['speed']
                description = data['weather'][0]['description']
                return {
                    'temp': round(temp),
                    'temp_min': round(temp_min),
                    'temp_max': round(temp_max),
                    'humidity': humidity,
                    'wind_speed': round(wind_speed),
                    'description': description,
                    'timestamp': datetime.now()
                }
    except Exception as e:
        logger.error(f"Weather fetch error: {e}")
        return None

def clothing_recommendation(temp):
    """Рекомендация по одежде на основе температуры."""
    if temp < -15:
        return "🥶 Очень холодно! Термобельё, пуховик, балаклава, подогрев руля обязателен."
    elif temp < -5:
        return "❄️ Холодно. Зимний комбез, тёплые перчатки, подшлемник."
    elif temp < 5:
        return "🧥 Прохладно. Демисезонный мотокомбез, флис, непромокаемые перчатки."
    elif temp < 15:
        return "🍂 Свежо. Куртка с подкладкой, длинные брюки, ветрозащита."
    elif temp < 25:
        return "🌤 Комфортно. Мотоджинсы, куртка-сетка, перчатки с вентиляцией."
    else:
        return "🔥 Жарко! Лёгкая экипировка с максимальной вентиляцией, обязательно пить воду."

async def get_forecast():
    """Возвращает прогноз на сегодня (минимум, максимум, описание)."""
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={WEATHER_CITY}&appid={WEATHER_API_KEY}&units=metric&lang=ru&cnt=8"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error(f"Forecast API error: {data}")
                    return None
                temps = [item['main']['temp'] for item in data['list']]
                temp_min = min(temps)
                temp_max = max(temps)
                # берём первое описание погоды
                desc = data['list'][0]['weather'][0]['description']
                return {
                    'temp_min': round(temp_min),
                    'temp_max': round(temp_max),
                    'description': desc,
                }
    except Exception as e:
        logger.error(f"Forecast error: {e}")
        return None