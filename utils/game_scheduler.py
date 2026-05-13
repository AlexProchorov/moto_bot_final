import asyncio
import logging
from datetime import datetime, timedelta
from database.crud import get_stale_game_by_timeout, finish_game_timeout

logger = logging.getLogger(__name__)

async def check_timeout_games():
    """Фоновая задача: проверяет каждые 30 секунд игры с таймаутом хода 5 минут."""
    while True:
        try:
            game = get_stale_game_by_timeout(timeout_minutes=5)
            if game:
                finish_game_timeout(game.id)
                logger.info(f"Game {game.id} finished due to timeout")
        except Exception as e:
            logger.error(f"Error in timeout checker: {e}")
        await asyncio.sleep(30)