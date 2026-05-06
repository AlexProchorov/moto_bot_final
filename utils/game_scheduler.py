import asyncio
import logging
from datetime import timedelta
from database.crud import auto_finish_stale_games

logger = logging.getLogger(__name__)

async def stale_games_cleaner():
    """Фоновая задача: каждые 6 часов завершает игры без хода более 7 дней."""
    while True:
        try:
            auto_finish_stale_games(timeout_hours=168)  # 7 дней
            logger.info("Checked for stale games")
        except Exception as e:
            logger.error(f"Error in stale games cleaner: {e}")
        await asyncio.sleep(21600)  # 6 часов
