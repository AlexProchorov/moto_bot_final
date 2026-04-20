import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN, LOG_LEVEL, GROUP_CHAT_ID, ADMIN_IDS
from database.engine import init_db, close_db
from utils.logger import setup_logger
from utils.mapping_loader import load_mapping
from handlers import registration, admin, common
from scheduler import start_scheduler
from utils.weather_scheduler import weather_scheduler_loop


from handlers import registration, admin, common, group_events   # Добавьте group_events
from handlers import ride_commands   
from utils.ride_scheduler import check_expired_active_users, check_expired_rides
from utils.ride_scheduler import cleanup_daily_topics
from utils.ride_scheduler import cleanup_daily_topics


logger = logging.getLogger(__name__)




async def set_commands(bot: Bot):
    common_commands = [
        BotCommand(command="start", description="Начать"),
        BotCommand(command="register", description="Регистрация"),
        BotCommand(command="my_profile", description="Моя анкета"),
        BotCommand(command="edit_my_profile", description="Редактировать анкету"),
        BotCommand(command="delete_my_profile", description="Удалить анкету"),
        BotCommand(command="weather_now", description="Погода сейчас"),
        BotCommand(command="ride_menu", description="🏍 Меню покатушек"),
        BotCommand(command="neighbors", description="Кто живёт в моём округе"), 
    ]
    await bot.set_my_commands(common_commands, scope=BotCommandScopeAllPrivateChats())

    admin_commands = [
        BotCommand(command="init", description="[Админ] Инициализировать регистрацию"),
        BotCommand(command="participants_info", description="[Админ] Список участников"),
        BotCommand(command="bd_info", description="[Админ] Дни рождения"),
        BotCommand(command="bd_info_soon", description="[Админ] Ближайшие ДР"),
        BotCommand(command="weather_on", description="[Админ] Вкл рассылку погоды"),
        BotCommand(command="weather_off", description="[Админ] Выкл рассылку погоды"),
        # Команды new_ride и end_ride НЕ добавляем в меню, чтобы не смешивались,
        # но они остаются рабочими для админов через ручной ввод или через кнопки в ride_menu.
    ]
    for admin_id in ADMIN_IDS:
        await bot.set_my_commands(common_commands + admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))

    await bot.set_my_commands([], scope=BotCommandScopeChat(chat_id=GROUP_CHAT_ID))

async def main():
    setup_logger(level=LOG_LEVEL)
    logger.info("Starting bot...")
    
    mapping = load_mapping()
    logger.info(f"Loaded mapping with {len(mapping)} brands")
  
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    start_scheduler(bot)
    registration.router.mapping = mapping
    asyncio.create_task(weather_scheduler_loop(bot))
    dp.include_router(registration.router)
    dp.include_router(admin.router)
    dp.include_router(common.router)
    dp.include_router(group_events.router)  
    dp.include_router(ride_commands.router)
    asyncio.create_task(check_expired_active_users(bot))
    asyncio.create_task(check_expired_rides(bot))
    asyncio.create_task(cleanup_daily_topics(bot))
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
