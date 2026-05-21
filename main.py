import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN, LOG_LEVEL, GROUP_CHAT_ID, ADMIN_IDS
from database.engine import init_db, close_db
from utils.logger import setup_logger
from utils.mapping_loader import load_mapping
from handlers import registration, admin, common, group_events, ride_commands
from scheduler import start_scheduler
from utils.weather_scheduler import weather_scheduler_loop
from utils.ride_scheduler import check_expired_active_users, check_expired_rides, cleanup_daily_topics
from middleware.admin_check import AdminCheckMiddleware
from handlers import tictactoe 
from aiohttp import ClientSession
from utils.game_scheduler import check_timeout_games
from handlers.announcement import router as announce_router

from aiohttp_socks import ProxyConnector
from aiogram import Bot
from handlers import ride_commands
from handlers.spam_handler import router as spam_router  
from handlers.wash_settings import router as wash_settings_router
from database.wash_crud import init_default_subtypes



logger = logging.getLogger(__name__)

async def set_commands(bot: Bot):
    common_commands = [
        BotCommand(command="start", description="Начать"),
        BotCommand(command="register", description="Регистрация"),
        BotCommand(command="my_profile", description="Моя анкета"),
        BotCommand(command="edit_my_profile", description="Редактировать анкету"),
        BotCommand(command="delete_my_profile", description="Удалить анкету"),
        BotCommand(command="neighbors", description="Мои соседи"),
        BotCommand(command="weather_now", description="Погода сейчас"),
        BotCommand(command="weather_settings", description="🌦 Вкл/выкл погоду"),
        BotCommand(command="ride_menu", description="🏍 Меню заездов"),
        BotCommand(command="games", description="🎲 Меню игр"),
        BotCommand(command="wash", description="🧼 Записаться на мойку"),
    ]

    # 1. Устанавливаем общие команды для всех (включая админов, но они перезапишутся позже)
    await bot.set_my_commands(common_commands, scope=BotCommandScopeAllPrivateChats())

    # 2. Админские команды (только для конкретных админов)
    admin_commands = [
        BotCommand(command="admin_panel", description="🏍 Меню админа"),
    ]

    for admin_id in ADMIN_IDS:
        try:
            # Проверяем, что бот может общаться с этим админом (он уже написал боту)
            await bot.get_chat(admin_id)
            # Устанавливаем команды: общие + админские
            await bot.set_my_commands(
                common_commands + admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception as e:
            # Если админ ещё не писал боту — пропускаем, команды установятся позже
            logger.warning(f"Не удалось установить команды для админа {admin_id}: {e}")
            continue

    # 3. В группе команды не нужны (очищаем)
    try:
        await bot.set_my_commands([], scope=BotCommandScopeChat(chat_id=GROUP_CHAT_ID))
    except Exception:
        pass  # группа может быть недоступна при локальном тестировании

async def main():
    setup_logger(level=LOG_LEVEL)
    logger.info("Starting bot...")
    
    mapping = load_mapping()
    logger.info(f"Loaded mapping with {len(mapping)} brands")
    
    init_db()

    bot = Bot(token=BOT_TOKEN)


    # Добавление исполнителей из .env
    
    
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage) 
    dp.message.middleware(AdminCheckMiddleware())
    dp.callback_query.middleware(AdminCheckMiddleware())
    init_default_subtypes()
    start_scheduler(bot)
    registration.router.mapping = mapping
    asyncio.create_task(weather_scheduler_loop(bot))
    
    dp.include_router(registration.router)
    dp.include_router(admin.router)
    dp.include_router(common.router)
    dp.include_router(group_events.router)
    dp.include_router(ride_commands.router)
    dp.include_router(tictactoe.router) 
    dp.include_router(spam_router)  
    dp.include_router(announce_router)
    dp.include_router(wash_settings_router) 
    asyncio.create_task(check_expired_active_users(bot))
    asyncio.create_task(check_expired_rides(bot))
    asyncio.create_task(cleanup_daily_topics(bot))
    asyncio.create_task(check_timeout_games())




    await set_commands(bot)
    
    try:
        await bot.send_message(chat_id=GROUP_CHAT_ID, text="Бот запущен")
        logger.info("Group access confirmed")
    except Exception as e:
        logger.error(f"Cannot send message to group: {e}")
    
    logger.info("Bot started polling")
    await dp.start_polling(bot)
    
    close_db()
    await bot.session.close()





if __name__ == "__main__":
    asyncio.run(main())
