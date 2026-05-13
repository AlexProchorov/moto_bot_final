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
    set_user_active, clear_user_active,
    get_user_active_topic_id, create_ride, get_active_rides,
    get_ride_by_id, add_participant, remove_participant,
    get_participants_count, end_ride, get_today_active_topic, create_today_active_topic,
    clear_today_active_topic
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

    # Если пользователь уже активен – не даём повторно активироваться
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user and user.active_until and user.active_until > datetime.now():
            await message.answer("✅ Вы уже активны и готовы катать. Статус действует до окончания 12 часов.\n"
                                 "Если вы хотите завершить активность, используйте «Не буду катать сегодня».")
            return

    # Получаем данные пользователя для упоминания
    tg_user = await message.bot.get_chat(user_id)
    display_name = f"{tg_user.first_name} (@{tg_user.username})" if tg_user.username else tg_user.first_name
    mention = f"<a href='tg://user?id={user_id}'>{display_name}</a>"

    # Проверяем, есть ли уже тема на сегодня (по БД)
    thread_id = get_today_active_topic()

    if thread_id:
        topic_link = f"https://t.me/c/{str(GROUP_CHAT_ID)[4:]}/{thread_id}"
        await message.answer(
            f"🏍 Тема для сегодняшних покатушек уже создана!\n"
            f"Присоединяйтесь: [Перейти в тему]({topic_link})\n"
            f"Ваш статус «готов катать» активирован на 12 часов.",
            parse_mode="Markdown"
        )
        set_user_active(user_id, hours=12, topic_id=thread_id)
        return

    # Создаём новую тему
    try:
        topic_name = f"{datetime.now().strftime('%d.%m')} - RIDE"
        topic = await message.bot.create_forum_topic(GROUP_CHAT_ID, name=topic_name)
        thread_id = topic.message_thread_id
        create_today_active_topic(thread_id)
    except Exception as e:
        logger.error(f"Ошибка создания темы: {e}")
        await message.answer("❌ Не удалось создать тему. Проверьте права бота и включение тем в группе.")
        return

    # Сообщение в новую тему
    await message.bot.send_message(
        GROUP_CHAT_ID,
        f"👤 {mention} инициировал покатушки!\nПрисоединяйтесь.",
        message_thread_id=thread_id,
        parse_mode="HTML"
    )

    # Анонс в общий чат
    topic_link = f"https://t.me/c/{str(GROUP_CHAT_ID)[4:]}/{thread_id}"
    await message.bot.send_message(
        GROUP_CHAT_ID,
        f"🏍 {mention} готов первым катать сегодня!\nПрисоединиться: [Перейти в тему]({topic_link})",
        parse_mode="HTML"
    )

    set_user_active(user_id, hours=12, topic_id=thread_id)
    await message.answer("✅ Вы активны 12 часов. Тема создана.")

# ---------- Логика "Не буду катать сегодня" ----------
async def stop_riding_logic(message: Message, user_id: int):
    clear_user_active(user_id)
    await message.answer("✅ Вы больше не активны. Тема покатушек останется в чате.")

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
    text = "🏍 *Активные райдеры:*\n\n" + "\n".join([f"• {u['name']} (@{u['username'] or 'нет'})" for u in users]) if users else "😴 Сейчас никто не катает."
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("rides"))
async def list_rides_cmd(message: Message):
    rides = get_active_rides()
    if not rides:
        await message.answer("📭 Нет запланированных заездов.")
        return
    text = "🗓 *Запланированные заезды:*\n\n"
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
        await message.answer("Используйте: /join <ID_заезда> (ID можно получить командой /rides)")
        return
    ride_id = int(parts[1])
    user_id = message.from_user.id

    if not add_participant(ride_id, user_id):
        await message.answer("❌ Вы уже участвуете или заезд не найден.")
        return

    # Получаем данные пользователя
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
    message_text = f"👤 {mention} ({bike}) присоединился к заезду!\n👥 Всего участников: {count}"

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
        await message.answer("Используйте: /leave <ID_заезда>")
        return
    ride_id = int(parts[1])
    remove_participant(ride_id, message.from_user.id)
    await message.answer(f"✅ Вы вышли из заезда №{ride_id}.")

# ---------- Админские команды ----------
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

    # 1. Создаём тему
    try:
        topic_name = f"{dt.strftime('%d.%m')} - PLAN RIDE"
        topic = await message.bot.create_forum_topic(GROUP_CHAT_ID, name=topic_name)
        thread_id = topic.message_thread_id
    except Exception as e:
        await message.answer("❌ Не удалось создать тему. Бот админ? Включены темы?")
        logger.error(f"Ошибка создания темы: {e}")
        await state.clear()
        return

    # 2. Отправляем правила покатушек в тему (теперь thread_id определён)
    from messages import ride_rules_message   # если импорт не сделан вверху файла
    await message.bot.send_message(
        GROUP_CHAT_ID,
        ride_rules_message(),
        message_thread_id=thread_id,
        parse_mode="Markdown"
    )

    # 3. Создаём заезд в БД
    ride_id = create_ride(title, dt, location, desc, admin_id, thread_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Участвую", callback_data=f"join_ride:{ride_id}")]])
    announcement = f"🎉 *Новый заезд: {title}*\n\n📅 {dt.strftime('%d.%m.%Y %H:%M')}\n📍 {location}\n📝 {desc}\n\n[Перейти в тему](https://t.me/c/{str(GROUP_CHAT_ID)[4:]}/{thread_id})"
    await message.bot.send_message(GROUP_CHAT_ID, announcement, parse_mode="Markdown", reply_markup=kb)
    await state.clear()
    await message.answer(f"✅ Заезд «{title}» создан!")

@router.message(Command("end_ride"))
async def end_ride_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для админов.")
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Используйте: /end_ride <id_заезда>")
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





@router.message(Command("ride_menu"))
async def ride_menu_cmd(message: Message):
    base_buttons = [
        [InlineKeyboardButton(text="🔥 ГОТОВ КАТАТЬ СЕГОДНЯ", callback_data="ride:ready")],
        [InlineKeyboardButton(text="🚫 Не буду катать сегодня", callback_data="ride:stop")],
        [InlineKeyboardButton(text="📅 Список запланированных заездов", callback_data="ride:list")],
        [InlineKeyboardButton(text="✅ Вступить в заезд", callback_data="ride:join_prompt")],
        [InlineKeyboardButton(text="❌ Отказаться от заезда", callback_data="ride:leave_prompt")],
    ]
    # Убираем админские кнопки полностью
    kb = InlineKeyboardMarkup(inline_keyboard=base_buttons)
    await message.answer("🏍 *Меню поездок* – выберите действие:", reply_markup=kb, parse_mode="Markdown")
@router.callback_query(F.data.startswith("ride:"))
async def ride_menu_actions(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    await callback.answer()
    user_id = callback.from_user.id
    logger.info(f"ride_menu_actions: user_id={user_id}, ADMIN_IDS={ADMIN_IDS}")

    if action == "ready":
        await ready_logic(callback.message, user_id)
    elif action == "stop":
        await stop_riding_logic(callback.message, user_id)
    elif action == "list":
        rides = get_active_rides()
        if not rides:
            await callback.message.answer("📭 Нет запланированных заездов.")
        else:
            text = "🗓 *Запланированные заезды:*\n\n"
            for ride in rides:
                count = get_participants_count(ride["id"])
                description = ride["description"] if ride["description"] else "—"
                text += (
                    f"*ID {ride['id']}.* *{ride['title']}*\n"
                    f"📅 {ride['date'].strftime('%d.%m.%Y %H:%M')}\n"
                    f"📝 Описание: {description}\n"
                    f"👥 Участников: {count}\n\n"
                )
            await callback.message.answer(text, parse_mode="Markdown")
    elif action == "join_prompt":
        await callback.message.answer("Введите ID заезда командой `/join <id>`")
    elif action == "leave_prompt":
        await callback.message.answer("Введите ID заезда командой `/leave <id>`")
    elif action == "new":
        if not is_admin(user_id):
            await callback.message.answer("⛔ Только для админов.")
            return
        logger.info(f"Вызов new_ride_cmd с admin_id={user_id}")
        await new_ride_cmd(callback.message, state, admin_id=user_id)
    elif action == "end_prompt":
        if not is_admin(user_id):
            await callback.message.answer("⛔ Только для админов.")
            return
        await callback.message.answer("Введите ID заезда для завершения: `/end_ride <id>`")
    else:
        await callback.message.answer("Действие недоступно.")

# ---------- Обработчик кнопки "Участвую" из анонса ----------
@router.callback_query(F.data.startswith("join_ride:"))
async def join_ride_callback(callback: CallbackQuery):
    ride_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    if not add_participant(ride_id, user_id):
        await callback.answer("Вы уже участвуете в этом заезде.", show_alert=True)
        return

    # Получаем данные пользователя
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            await callback.answer("❌ Вы не зарегистрированы. Используйте /start.")
            return
        user_name = user.name
        bike = f"{user.bike_brand} {user.bike_model}".strip() or "не указан"
        username = user.username or user_name

    ride = get_ride_by_id(ride_id)
    if not ride:
        await callback.answer("❌ Заезд не найден.")
        return

    count = get_participants_count(ride_id)
    mention = f"<a href='tg://user?id={user_id}'>{username}</a>"
    message_text = f"👤 {mention} ({bike}) присоединился к заезду!\n👥 Всего участников: {count}"

    if ride["message_thread_id"]:
        try:
            await callback.bot.send_message(
                GROUP_CHAT_ID,
                message_text,
                message_thread_id=ride["message_thread_id"],
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение в тему заезда {ride_id}: {e}")

    await callback.answer("Вы записаны на заезд!")


