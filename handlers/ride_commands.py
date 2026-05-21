import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from messages import ride_rules_message
from config import GROUP_CHAT_ID, ADMIN_IDS
from database.engine import get_session
from database.models import User
from database.crud import (
    set_user_active, clear_user_active, get_user_active_topic_id,
    create_ride, get_active_rides, get_ride_by_id, add_participant,
    remove_participant, get_participants_count, end_ride,
    get_today_active_topic, create_today_active_topic, clear_today_active_topic,
    get_active_users
)

logger = logging.getLogger(__name__)
router = Router(name="ride_commands")

# Приводим ADMIN_IDS к списку целых чисел
ADMIN_IDS = [int(uid) for uid in ADMIN_IDS]

def is_admin(uid: int) -> bool:
    uid = int(uid)
    result = uid in ADMIN_IDS
    logger.info(f"is_admin: uid={uid}, ADMIN_IDS={ADMIN_IDS}, result={result}")
    if not result:
        logger.warning(f"Доступ запрещён: uid={uid}, ADMIN_IDS={ADMIN_IDS}")
    return result

# ---------- FSM для создания заезда (админ) ----------
class CreateRideStates(StatesGroup):
    waiting_title = State()
    waiting_date = State()
    waiting_time = State()
    waiting_location = State()
    waiting_description = State()

# ---------- Логика "Готов катать сегодня" ----------
async def ready_logic(message: Message, user_id: int):
    # Проверка регистрации
    with get_session() as session:
        user_db = session.query(User).filter(User.telegram_id == user_id).first()
        if not user_db:
            await message.answer("❌ Вы не зарегистрированы. Используйте /start.")
            return

    # Получаем данные пользователя для упоминания
    tg_user = await message.bot.get_chat(user_id)
    display_name = f"{tg_user.first_name} (@{tg_user.username})" if tg_user.username else tg_user.first_name
    mention = f"<a href='tg://user?id={user_id}'>{display_name}</a>"
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        bike = f"{user.bike_brand} {user.bike_model}".strip() or "не указан"

    # Проверяем, есть ли уже тема на сегодня
    thread_id = get_today_active_topic()
    if thread_id:
        # Тема уже существует – просто активируем пользователя и шлём уведомление в тему
        if get_user_active_topic_id(user_id) == thread_id:
            await message.answer("✅ Вы уже активны в текущей теме.")
            return

        set_user_active(user_id, hours=12, topic_id=thread_id)
        # Отправляем сообщение в тему о присоединении
        try:
            await message.bot.send_message(
                GROUP_CHAT_ID,
                f"🏍️ {mention} ({bike}) готов катать сегодня!\nВсего активных: {len(get_active_users())}",
                message_thread_id=thread_id,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение в тему {thread_id}: {e}")
        await message.answer("✅ Вы активированы на 12 часов. Тема уже существует.")
        return

    # Создаём новую тему
    try:
        topic_name = f"{datetime.now().strftime('%d.%m')} - READY"
        topic = await message.bot.create_forum_topic(GROUP_CHAT_ID, name=topic_name)
        thread_id = topic.message_thread_id
        create_today_active_topic(thread_id)
    except Exception as e:
        logger.error(f"Ошибка создания темы: {e}")
        await message.answer("❌ Не удалось создать тему. Проверьте права бота и включение тем в группе.")
        return

    # Сообщение в новой теме с инлайн-кнопками
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готов катать сегодня", callback_data="ready_today:join")],
        [InlineKeyboardButton(text="❌ Не буду катать сегодня", callback_data="ready_today:leave")]
    ])
    await message.bot.send_message(
        GROUP_CHAT_ID,
        f"🏍️ {mention} инициировал покатушки!\nНажмите кнопку, чтобы присоединиться.",
        message_thread_id=thread_id,
        parse_mode="HTML",
        reply_markup=kb
    )

    # Анонс в общий чат со ссылкой на тему (теперь HTML)
    topic_link = f"https://t.me/c/{str(GROUP_CHAT_ID)[4:]}/{thread_id}"
    await message.bot.send_message(
        GROUP_CHAT_ID,
        f"🏍️ {mention} готов первым катать сегодня!\nПрисоединиться: <a href='{topic_link}'>Перейти в тему</a>",
        parse_mode="HTML"
    )

    set_user_active(user_id, hours=12, topic_id=thread_id)
    await message.answer("✅ Вы активны 12 часов. Тема создана.")

# ---------- Логика "Не буду катать сегодня" ----------
async def stop_riding_logic(message: Message, user_id: int):
    thread_id = get_user_active_topic_id(user_id)
    if thread_id:
        # Уведомляем тему о выходе
        try:
            tg_user = await message.bot.get_chat(user_id)
            display_name = f"{tg_user.first_name} (@{tg_user.username})" if tg_user.username else tg_user.first_name
            mention = f"<a href='tg://user?id={user_id}'>{display_name}</a>"
            with get_session() as session:
                user = session.query(User).filter(User.telegram_id == user_id).first()
                bike = f"{user.bike_brand} {user.bike_model}".strip() or "не указан"
            await message.bot.send_message(
                GROUP_CHAT_ID,
                f"🚫 {mention} ({bike}) больше не катает сегодня.",
                message_thread_id=thread_id,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение о выходе в тему {thread_id}: {e}")
    clear_user_active(user_id)
    await message.answer("✅ Вы больше не активны.")

# ---------- Команды для ручного ввода ----------
@router.message(Command("ready"))
async def ready_cmd(message: Message):
    if message.chat.type != "private":
        await message.answer("Доступно только в ЛС.")
        return
    await ready_logic(message, message.from_user.id)

@router.message(Command("stop_riding"))
async def stop_riding_cmd(message: Message):
    if message.chat.type != "private":
        await message.answer("Доступно только в ЛС.")
        return
    await stop_riding_logic(message, message.from_user.id)

@router.message(Command("active_riders"))
async def active_riders_cmd(message: Message):
    users = get_active_users()
    text = "🏍️ *Активные райдеры:*\n\n" + "\n".join([f"• {u['name']} (@{u['username'] or 'нет'})" for u in users]) if users else "🧘‍♂️ Сейчас никто не катает."
    await message.answer(text, parse_mode="Markdown")

# ---------- Плановые заезды (админ) ----------
@router.message(Command("rides"))
async def list_rides_cmd(message: Message):
    rides = get_active_rides()
    if not rides:
        await message.answer("📭 Нет запланированных заездов.")
        return
    text = "🏁 *Запланированные заезды:*\n\n"
    for ride in rides:
        count = get_participants_count(ride["id"])
        description = ride["description"] if ride["description"] else "—"
        text += (
            f"*ID {ride['id']}.* *{ride['title']}*\n"
            f"📅 {ride['date'].strftime('%d.%m.%Y %H:%M')}\n"
            f"📝 Описание: {description}\n"
            f"👥 Участников: {count}\n\n"
        )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("join"))
async def join_ride_text(message: Message):
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Используйте: /join <ID> (ID можно получить командой /rides)")
        return
    ride_id = int(parts[1])
    user_id = message.from_user.id

    if not add_participant(ride_id, user_id):
        await message.answer("❌ Вы уже участвуете или заезд не найден.")
        return

    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Используйте /start.")
            return
        user_name = user.name
        bike = f"{user.bike_brand} {user.bike_model}".strip() or "не указан"
        username = user.username or user_name

    ride = get_ride_by_id(ride_id)
    if not ride:
        await message.answer("❌ Заезд не найден.")
        return

    count = get_participants_count(ride_id)
    mention = f"<a href='tg://user?id={user_id}'>{username}</a>"
    message_text = f"🏍️ {mention} ({bike}) присоединился к заезду!\nВсего участников: {count}"

    if ride["message_thread_id"]:
        try:
            await message.bot.send_message(
                GROUP_CHAT_ID,
                message_text,
                message_thread_id=ride["message_thread_id"],
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение в тему заезда {ride_id}: {e}")
    await message.answer(f"✅ Вы записаны на заезд №{ride_id}.")

@router.message(Command("leave"))
async def leave_ride_text(message: Message):
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Используйте: /leave <ID>")
        return
    ride_id = int(parts[1])
    remove_participant(ride_id, message.from_user.id)
    await message.answer(f"✅ Вы вышли из заезда №{ride_id}.")

# ---------- Админские команды (плановые заезды) ----------
@router.message(Command("new_ride"))
async def new_ride_cmd(message: Message, state: FSMContext, admin_id: int = None):
    effective_admin_id = admin_id if admin_id is not None else message.from_user.id
    if not is_admin(effective_admin_id):
        await message.answer("⛔ Только для админов.")
        return
    await state.update_data(admin_id=effective_admin_id)
    await state.set_state(CreateRideStates.waiting_title)
    await message.answer("Введите название заезда:")

@router.message(CreateRideStates.waiting_title)
async def process_ride_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateRideStates.waiting_date)
    await message.answer("Введите дату в формате ДД.ММ.ГГГГ (например, 15.05.2025):")

@router.message(CreateRideStates.waiting_date)
async def process_ride_date(message: Message, state: FSMContext):
    try:
        date_obj = datetime.strptime(message.text.strip(), "%d.%m.%Y")
        await state.update_data(date=date_obj)
        await state.set_state(CreateRideStates.waiting_time)
        await message.answer("Введите время в формате ЧЧ:ММ (например, 19:00):")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте ДД.ММ.ГГГГ")

@router.message(CreateRideStates.waiting_time)
async def process_ride_time(message: Message, state: FSMContext):
    try:
        hour, minute = map(int, message.text.strip().split(':'))
        data = await state.get_data()
        dt = data['date'].replace(hour=hour, minute=minute)
        await state.update_data(datetime=dt)
        await state.set_state(CreateRideStates.waiting_location)
        await message.answer("Введите место встречи:")
    except:
        await message.answer("❌ Неверный формат. Используйте ЧЧ:ММ")

@router.message(CreateRideStates.waiting_location)
async def process_ride_location(message: Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    await state.set_state(CreateRideStates.waiting_description)
    await message.answer("Введите описание заезда (можно пропустить, отправив '-'):")

@router.message(CreateRideStates.waiting_description)
async def process_ride_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc == "-":
        desc = ""

    data = await state.get_data()
    title = data['title']
    dt = data['datetime']
    location = data['location']
    admin_id = data.get('admin_id', message.from_user.id)

    # 1. Создаём тему для планового заезда
    try:
        topic_name = f"{dt.strftime('%d.%m')} - PLAN RIDE"
        topic = await message.bot.create_forum_topic(GROUP_CHAT_ID, name=topic_name)
        thread_id = topic.message_thread_id
    except Exception as e:
        await message.answer("❌ Не удалось создать тему. Бот админ? Включены темы?")
        logger.error(f"Ошибка создания темы: {e}")
        await state.clear()
        return

    # 2. Отправляем правила покатушек в тему (Markdown)
    await message.bot.send_message(
        GROUP_CHAT_ID,
        ride_rules_message(),
        message_thread_id=thread_id,
        parse_mode="Markdown"
    )

    # 3. Создаём заезд в БД
    ride_id = create_ride(title, dt, location, desc, admin_id, thread_id)

    # 4. Сообщение о заезде в теме (Markdown для форматирования, без HTML)
    announcement_in_topic = (
        f"🏁 *НОВЫЙ ПЛАНОВЫЙ ЗАЕЗД!*\n\n"
        f"*Название:* {title}\n"
        f"*Дата и время:* {dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"*Место встречи:* {location}\n"
        f"*Описание:* {desc if desc else '—'}\n\n"
        f"👇 Нажмите кнопку, чтобы подтвердить участие:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Участвую", callback_data=f"join_ride:{ride_id}")]
    ])

    await message.bot.send_message(
        GROUP_CHAT_ID,
        announcement_in_topic,
        message_thread_id=thread_id,
        parse_mode="Markdown",
        reply_markup=kb
    )

    await state.clear()
    await message.answer(f"✅ Заезд «{title}» создан! Информация о заезде находится в созданной теме.")

@router.message(Command("end_ride"))
async def end_ride_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Используйте: /end_ride <ID>")
        return
    ride_id = int(parts[1])
    ride = get_ride_by_id(ride_id)
    if not ride:
        await message.answer("❌ Заезд не найден.")
        return
    if ride["message_thread_id"]:
        try:
            await message.bot.delete_forum_topic(GROUP_CHAT_ID, ride["message_thread_id"])
            logger.info(f"Удалена тема заезда {ride_id}")
        except Exception as e:
            logger.error(f"Ошибка удаления темы: {e}")
    end_ride(ride_id)
    await message.answer(f"✅ Заезд «{ride['title']}» завершён и удалён.")
    await message.bot.send_message(GROUP_CHAT_ID, f"🏁 Заезд «{ride['title']}» завершён. Тема удалена.")

# ---------- Обработчик кнопки участия в плановом заезде ----------
@router.callback_query(F.data.startswith("join_ride:"))
async def join_ride_callback(callback: CallbackQuery):
    ride_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    if not add_participant(ride_id, user_id):
        await callback.answer("❌ Вы уже участвуете в этом заезде или заезд не найден.", show_alert=True)
        return

    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await callback.answer("❌ Вы не зарегистрированы. Используйте /start.", show_alert=True)
            return
        username = user.username or user.name
        bike = f"{user.bike_brand} {user.bike_model}".strip() or "не указан"

    ride = get_ride_by_id(ride_id)
    if not ride or not ride.get("message_thread_id"):
        await callback.answer("❌ Не удалось найти тему заезда.", show_alert=True)
        return

    count = get_participants_count(ride_id)
    mention = f"<a href='tg://user?id={user_id}'>{username}</a>"
    message_text = f"🏍️ {mention} ({bike}) присоединился к заезду!\nВсего участников: {count}"

    await callback.message.bot.send_message(
        GROUP_CHAT_ID,
        message_text,
        message_thread_id=ride["message_thread_id"],
        parse_mode="HTML"
    )

    await callback.answer("✅ Вы записаны на заезд!", show_alert=False)

# ---------- Обработчики кнопок для READY-темы ----------
@router.callback_query(F.data == "ready_today:join")
async def ready_today_join_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    thread_id = get_today_active_topic()

    if not thread_id:
        await callback.answer("❌ Нет активной темы для покатушек. Используйте /ready в ЛС, чтобы создать.", show_alert=True)
        return

    # Проверяем, не активен ли уже пользователь в этой теме
    if get_user_active_topic_id(user_id) == thread_id:
        await callback.answer("✅ Вы уже активны в текущей теме!", show_alert=False)
        return

    # Проверка регистрации
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await callback.answer("❌ Вы не зарегистрированы. Используйте /start.", show_alert=True)
            return
        bike = f"{user.bike_brand} {user.bike_model}".strip() or "не указан"
        username = user.username or user.name

    set_user_active(user_id, hours=12, topic_id=thread_id)

    mention = f"<a href='tg://user?id={user_id}'>{username}</a>"
    active_count = len(get_active_users())

    try:
        await callback.bot.send_message(
            GROUP_CHAT_ID,
            f"🏍️ {mention} ({bike}) готов катать сегодня!\nВсего активных: {active_count}",
            message_thread_id=thread_id,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение в тему {thread_id}: {e}")

    await callback.answer("✅ Вы активированы на 12 часов!", show_alert=False)

@router.callback_query(F.data == "ready_today:leave")
async def ready_today_leave_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    thread_id = get_user_active_topic_id(user_id)

    if not thread_id:
        await callback.answer("❌ Вы не активны в текущей теме.", show_alert=False)
        return

    # Получаем данные для уведомления
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            bike = f"{user.bike_brand} {user.bike_model}".strip() or "не указан"
            username = user.username or user.name
        else:
            bike = "байк не указан"
            username = "Пользователь"

    mention = f"<a href='tg://user?id={user_id}'>{username}</a>"
    try:
        await callback.bot.send_message(
            GROUP_CHAT_ID,
            f"🚫 {mention} ({bike}) больше не катает сегодня.",
            message_thread_id=thread_id,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение о выходе в тему {thread_id}: {e}")

    clear_user_active(user_id)
    await callback.answer("✅ Вы вышли из активности.", show_alert=False)

# ---------- Меню управления заездами ----------
@router.message(Command("ride_menu"))
async def ride_menu_cmd(message: Message):
    base_buttons = [
        [InlineKeyboardButton(text="🏍️ ГОТОВ КАТАТЬ СЕГОДНЯ", callback_data="ride:ready")],
        [InlineKeyboardButton(text="🚫 Не буду катать сегодня", callback_data="ride:stop")],
        [InlineKeyboardButton(text="📋 Список запланированных заездов", callback_data="ride:list")],
        [InlineKeyboardButton(text="👥 Активные райдеры", callback_data="ride:active")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="ride:close")]
    ]
    #if is_admin(message.from_user.id):
        #base_buttons.append([InlineKeyboardButton(text="🛠️ Админ-панель заездов", callback_data="ride:admin_panel")])
    kb = InlineKeyboardMarkup(inline_keyboard=base_buttons)
    await message.answer("🏍️ Меню управления заездами:", reply_markup=kb)

@router.callback_query(F.data == "ride:ready")
async def ride_ready_callback(callback: CallbackQuery):
    await callback.answer()
    await ready_logic(callback.message, callback.from_user.id)

@router.callback_query(F.data == "ride:stop")
async def ride_stop_callback(callback: CallbackQuery):
    await callback.answer()
    await stop_riding_logic(callback.message, callback.from_user.id)

@router.callback_query(F.data == "ride:list")
async def ride_list_callback(callback: CallbackQuery):
    await callback.answer()
    await list_rides_cmd(callback.message)

@router.callback_query(F.data == "ride:active")
async def ride_active_callback(callback: CallbackQuery):
    await callback.answer()
    await active_riders_cmd(callback.message)

@router.callback_query(F.data == "ride:close")
async def ride_close_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data == "ride:admin_panel")
async def ride_admin_panel_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Только для админов.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Создать новый плановый заезд", callback_data="ride:new")],
        [InlineKeyboardButton(text="🔚 Завершить заезд", callback_data="ride:end")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ride:menu")]
    ])
    await callback.message.edit_text("🛠️ Админ-панель управления заездами:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "ride:new")
async def ride_new_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Только для админов.", show_alert=True)
        return
    await callback.answer()
    await new_ride_cmd(callback.message, state, admin_id=callback.from_user.id)

@router.callback_query(F.data == "ride:end")
async def ride_end_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Только для админов.", show_alert=True)
        return
    await callback.answer()
    rides = get_active_rides()
    if not rides:
        await callback.message.answer("📭 Нет активных заездов для завершения.")
        return
    buttons = []
    for ride in rides:
        buttons.append([InlineKeyboardButton(text=f"{ride['title']} ({ride['date'].strftime('%d.%m')})", callback_data=f"ride:end_confirm:{ride['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ride:admin_panel")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите заезд для завершения:", reply_markup=kb)

@router.callback_query(F.data.startswith("ride:end_confirm:"))
async def ride_end_confirm_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Только для админов.", show_alert=True)
        return
    ride_id = int(callback.data.split(":")[2])
    ride = get_ride_by_id(ride_id)
    if not ride:
        await callback.answer("❌ Заезд не найден.")
        return
    if ride["message_thread_id"]:
        try:
            await callback.bot.delete_forum_topic(GROUP_CHAT_ID, ride["message_thread_id"])
            logger.info(f"Удалена тема заезда {ride_id}")
        except Exception as e:
            logger.error(f"Ошибка удаления темы: {e}")
    end_ride(ride_id)
    await callback.answer(f"✅ Заезд «{ride['title']}» завершён и удалён.", show_alert=True)
    await callback.message.edit_text(f"🏁 Заезд «{ride['title']}» завершён. Тема удалена.")
    await callback.bot.send_message(GROUP_CHAT_ID, f"🏁 Заезд «{ride['title']}» завершён. Тема удалена.")

@router.callback_query(F.data == "ride:menu")
async def ride_menu_back_callback(callback: CallbackQuery):
    await callback.answer()
    await ride_menu_cmd(callback.message)