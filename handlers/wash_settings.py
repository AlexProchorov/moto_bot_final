import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from config import ADMIN_IDS, GROUP_CHAT_ID
from database.wash_crud import (
    get_or_create_service, update_service, get_subtypes, update_subtype_price,
    get_all_schedules, update_schedule, is_worker, add_worker, get_all_workers, delete_worker
)
from database.wash_crud import init_default_subtypes
import asyncio

logger = logging.getLogger(__name__)
router = Router(name="wash_settings")

# ---------- FSM для разных операций ----------
class EditAddressState(StatesGroup):
    waiting_address = State()

class EditPriceState(StatesGroup):
    waiting_subtype = State()
    waiting_price = State()

class EditHoursState(StatesGroup):
    choosing_day = State()
    selecting_hours = State()

class AddPhotoState(StatesGroup):
    waiting_photo = State()

class EditDescriptionState(StatesGroup):
    waiting_description = State()

# ---------- Вспомогательная проверка: может ли пользователь управлять мойкой ----------
def can_manage(uid: int) -> bool:
    return uid in ADMIN_IDS or is_worker(uid)

# ---------- Клавиатура главного меню ----------
def main_menu_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Текущие настройки", callback_data="wash:show")],
        [InlineKeyboardButton(text="📅 Расписание (дни/часы)", callback_data="wash:schedule")],
        [InlineKeyboardButton(text="💰 Стоимость мойки", callback_data="wash:price")],
        [InlineKeyboardButton(text="🔌 Работа мойки (вкл/выкл)", callback_data="wash:toggle_active")],
        [InlineKeyboardButton(text="📍 Адрес мойки", callback_data="wash:address")],
        [InlineKeyboardButton(text="🖼 Фотографии мойки", callback_data="wash:photos")],
        [InlineKeyboardButton(text="📝 Описание мойки", callback_data="wash:description")],
        [InlineKeyboardButton(text="👥 Управление исполнителями", callback_data="wash:workers")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="wash:back_to_admin")]
    ])
    return kb

# ---------- Команда /wash_settings (доступна только исполнителям и админам) ----------
@router.message(Command("wash_settings"))
async def cmd_wash_settings(message: Message):
    if not can_manage(message.from_user.id):
        await message.answer("⛔ Доступно только исполнителям и администраторам.")
        return
    await message.answer("🧼 *Настройки мойки*", parse_mode="Markdown", reply_markup=main_menu_kb())

# ---------- Интеграция в админ-панель (добавляем кнопку) ----------
# Мы добавим кнопку в admin.py позже, а здесь просто обработчик для callback "admin:wash_settings"
@router.callback_query(F.data == "admin:wash_settings")
async def admin_wash_settings(callback: CallbackQuery):
    if not can_manage(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    await callback.message.edit_text("🧼 *Настройки мойки*", parse_mode="Markdown", reply_markup=main_menu_kb())
    await callback.answer()

# ---------- 1. Показать текущие настройки ----------
@router.callback_query(F.data == "wash:show")
async def show_settings(callback: CallbackQuery):
    service = get_or_create_service()
    subtypes = get_subtypes()
    schedules = get_all_schedules()
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    status = "🟢 Работает" if service.is_active else "🔴 Не работает"
    text = f"🧼 *Текущие настройки мойки*\n\n"
    text += f"*Статус:* {status}\n"
    text += f"*Адрес:* {service.address or 'не указан'}\n"
    text += f"*Описание:* {service.description or 'не указано'}\n\n"
    text += f"*Стоимость:*\n"
    for s in subtypes:
        text += f"• {s.name}: {s.price} руб.\n"
    text += f"\n*Расписание:*\n"
    for sched in schedules:
        day_name = days[sched.day_of_week]
        if not sched.is_working:
            text += f"{day_name}: выходной\n"
        else:
            hours_str = ", ".join(f"{h}:00" for h in sorted(sched.hours))
            text += f"{day_name}: {hours_str}\n"
    text += f"\n*Фотографий:* {len(service.photos)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "wash:menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text("🧼 *Настройки мойки*", parse_mode="Markdown", reply_markup=main_menu_kb())
    await callback.answer()

# ---------- 2. Расписание (выбор дня) ----------
@router.callback_query(F.data == "wash:schedule")
async def schedule_choose_day(callback: CallbackQuery):
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    kb_buttons = []
    for i, day in enumerate(days):
        kb_buttons.append([InlineKeyboardButton(text=day, callback_data=f"wash_sched_day:{i}")])
    kb_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    await callback.message.edit_text("Выберите день для настройки:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("wash_sched_day:"))
async def schedule_day_selected(callback: CallbackQuery, state: FSMContext):
    day = int(callback.data.split(":")[1])
    await state.update_data(day=day)
    sched = get_all_schedules()[day]
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    status = "рабочий" if sched.is_working else "выходной"
    hours_str = ", ".join(f"{h}:00" for h in sorted(sched.hours)) if sched.is_working else "—"
    text = f"*{days[day]}*\nСтатус: {status}\nЧасы: {hours_str}\n\nЧто хотите изменить?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переключить рабочий/выходной", callback_data="wash_toggle_day")],
        [InlineKeyboardButton(text="⏰ Изменить часы работы", callback_data="wash_edit_hours")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="wash:schedule")]
    ])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "wash_toggle_day")
async def toggle_day_off(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data["day"]
    sched = get_all_schedules()[day]
    new_status = not sched.is_working
    update_schedule(day, is_working=new_status)
    await callback.answer("Статус изменён.")
    # Вернуться к настройке дня
    await schedule_day_selected(callback, state)

@router.callback_query(F.data == "wash_edit_hours")
async def edit_hours_prompt(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data["day"]
    sched = get_all_schedules()[day]
    current_hours = sched.hours if sched.is_working else []
    # Создаём клавиатуру с часами от 9 до 20
    hour_buttons = []
    for hour in range(9, 21):
        is_selected = hour in current_hours
        mark = "✅" if is_selected else "⬜"
        hour_buttons.append(InlineKeyboardButton(text=f"{mark} {hour}:00", callback_data=f"wash_hour_toggle:{hour}"))
    rows = [hour_buttons[i:i+4] for i in range(0, len(hour_buttons), 4)]
    rows.append([InlineKeyboardButton(text="✅ Сохранить", callback_data="wash_hours_save")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash_sched_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await state.set_state(EditHoursState.selecting_hours)
    await state.update_data(selected_hours=current_hours.copy())
    await callback.message.edit_text("Выберите часы работы (нажмите на час, чтобы включить/выключить):", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("wash_hour_toggle:"))
async def toggle_hour(callback: CallbackQuery, state: FSMContext):
    hour = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = data.get("selected_hours", [])
    if hour in selected:
        selected.remove(hour)
    else:
        selected.append(hour)
    await state.update_data(selected_hours=selected)
    # Обновляем клавиатуру
    await edit_hours_prompt(callback, state)

@router.callback_query(F.data == "wash_hours_save")
async def save_hours(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data["day"]
    selected = data.get("selected_hours", [])
    selected.sort()
    update_schedule(day, hours=selected, is_working=True)
    await state.clear()
    await callback.answer("Расписание сохранено.")
    # Возврат к настройке дня
    await schedule_day_selected(callback, state)

@router.callback_query(F.data == "wash_sched_back")
async def hours_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await schedule_day_selected(callback, state)

# ---------- 3. Стоимость мойки ----------
@router.callback_query(F.data == "wash:price")
async def price_menu(callback: CallbackQuery, state: FSMContext):
    subtypes = get_subtypes()
    if not subtypes:
        await callback.message.answer("Нет настроек стоимости.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s.name} ({s.price} руб.)", callback_data=f"wash_price_edit:{s.id}")] for s in subtypes
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")])
    await callback.message.edit_text("Выберите тип мойки для изменения цены:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("wash_price_edit:"))
async def price_edit(callback: CallbackQuery, state: FSMContext):
    subtype_id = int(callback.data.split(":")[1])
    await state.update_data(subtype_id=subtype_id)
    await state.set_state(EditPriceState.waiting_price)
    await callback.message.edit_text("Введите новую цену (число, только рубли):")
    await callback.answer()

@router.message(EditPriceState.waiting_price)
async def price_received(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите число.")
        return
    price = int(message.text)
    data = await state.get_data()
    subtype_id = data["subtype_id"]
    update_subtype_price(subtype_id, price)
    await state.clear()
    await message.answer("✅ Цена обновлена.")
    # Показать главное меню
    await cmd_wash_settings(message)

# ---------- 4. Включить/выключить работу мойки ----------
@router.callback_query(F.data == "wash:toggle_active")
async def toggle_active(callback: CallbackQuery):
    service = get_or_create_service()
    new_status = not service.is_active
    update_service(is_active=new_status)
    status_text = "включена" if new_status else "выключена"
    await callback.message.edit_text(f"✅ Работа мойки {status_text}.")
    await asyncio.sleep(1)
    await back_to_menu(callback)
    await callback.answer()

# ---------- 5. Адрес мойки ----------
@router.callback_query(F.data == "wash:address")
async def edit_address_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditAddressState.waiting_address)
    await callback.message.edit_text("Введите новый адрес мойки:")
    await callback.answer()

@router.message(EditAddressState.waiting_address)
async def address_received(message: Message, state: FSMContext):
    address = message.text.strip()
    update_service(address=address)
    await state.clear()
    await message.answer("✅ Адрес обновлён.")
    await cmd_wash_settings(message)

# ---------- 6. Фотографии мойки ----------
@router.callback_query(F.data == "wash:photos")
async def photos_menu(callback: CallbackQuery):
    service = get_or_create_service()
    photos = service.photos
    text = f"*Фотографии мойки* ({len(photos)} шт.)\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фото", callback_data="wash:add_photo")],
        [InlineKeyboardButton(text="🗑 Удалить все фото", callback_data="wash:del_photos")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")]
    ])
    # Если есть фото, показываем первые три (нельзя много в одном сообщении)
    if photos:
        media = []
        for i, file_id in enumerate(photos[:3]):
            media.append(InputMediaPhoto(media=file_id, caption=text if i==0 else ""))
        try:
            await callback.message.delete()
            await callback.message.answer_media_group(media=media)
            await callback.message.answer("Управление фотографиями:", reply_markup=kb)
        except Exception as e:
            logger.error(f"Не удалось показать фото: {e}")
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "wash:add_photo")
async def add_photo_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddPhotoState.waiting_photo)
    await callback.message.edit_text("Отправьте фотографию (можно несколько, отправляйте по одной, после каждой нажимайте 'Готово'):\nИли нажмите /cancel для отмены.")
    await callback.answer()

@router.message(AddPhotoState.waiting_photo, F.photo)
async def photo_received(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ Фото добавлено. Всего: {len(photos)}. Отправьте ещё или нажмите /done для завершения.")

@router.message(Command("done"))
async def finish_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if photos:
        service = get_or_create_service()
        # объединяем с существующими (лимит 10)
        all_photos = (service.photos or []) + photos
        if len(all_photos) > 10:
            all_photos = all_photos[:10]
        update_service(photos=all_photos)
        await message.answer(f"✅ Сохранено {len(photos)} новых фото. Всего фото: {len(all_photos)}.")
    else:
        await message.answer("Нет новых фото.")
    await state.clear()
    await cmd_wash_settings(message)

@router.callback_query(F.data == "wash:del_photos")
async def delete_all_photos(callback: CallbackQuery):
    update_service(photos=[])
    await callback.message.edit_text("✅ Все фотографии удалены.")
    await asyncio.sleep(1)
    await photos_menu(callback)
    await callback.answer()

# ---------- 7. Описание мойки ----------
@router.callback_query(F.data == "wash:description")
async def edit_description_prompt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditDescriptionState.waiting_description)
    await callback.message.edit_text("Введите новое описание мойки (текст):")
    await callback.answer()

@router.message(EditDescriptionState.waiting_description)
async def description_received(message: Message, state: FSMContext):
    desc = message.text.strip()
    update_service(description=desc)
    await state.clear()
    await message.answer("✅ Описание обновлено.")
    await cmd_wash_settings(message)

# ---------- 8. Управление исполнителями ----------
@router.callback_query(F.data == "wash:workers")
async def workers_menu(callback: CallbackQuery):
    workers = get_all_workers()
    text = "👥 *Исполнители*\n\n"
    for w in workers:
        text += f"• {w.name} (ID {w.user_id})\n"
    text += "\n➕ Добавить – /add_worker ID Имя\n🗑 Удалить – /del_worker ID"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")]])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@router.message(Command("add_worker"))
async def add_worker_cmd(message: Message):
    if not can_manage(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("❌ Используйте: /add_worker <telegram_id> <имя>")
        return
    try:
        tid = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return
    name = args[2]
    add_worker(tid, name)
    await message.answer(f"✅ Исполнитель {name} (ID {tid}) добавлен.")

@router.message(Command("del_worker"))
async def del_worker_cmd(message: Message):
    if not can_manage(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("❌ Используйте: /del_worker <telegram_id>")
        return
    tid = int(args[1])
    delete_worker(tid)
    await message.answer(f"✅ Исполнитель с ID {tid} удалён.")

# ---------- 9. Назад в админ-панель ----------
@router.callback_query(F.data == "wash:back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    from handlers.admin import admin_panel_cmd
    await admin_panel_cmd(callback.message)
    await callback.answer()