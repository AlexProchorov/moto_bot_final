import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_IDS
from database.wash_crud import (
    get_or_create_wash_service, update_service, get_subtypes, update_subtype_price,
    get_all_schedules, update_schedule, is_worker, add_worker, get_all_workers, delete_worker,
    get_worker_by_telegram_id, regenerate_slots_for_worker
)
import asyncio

logger = logging.getLogger(__name__)
router = Router(name="wash_settings")

WORKER_TELEGRAM_ID = 194851131

def get_fixed_worker_id() -> int | None:
    worker = get_worker_by_telegram_id(WORKER_TELEGRAM_ID)
    return worker.id if worker else None

class EditAddressState(StatesGroup):
    waiting_address = State()
class EditDescriptionState(StatesGroup):
    waiting_description = State()
class EditPriceState(StatesGroup):
    waiting_price = State()
class AddPhotoState(StatesGroup):
    waiting_photo = State()
class EditHoursState(StatesGroup):
    selecting_hours = State()

def can_manage(uid: int) -> bool:
    return uid in ADMIN_IDS or is_worker(uid)

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
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

@router.message(Command("wash_settings"))
async def cmd_wash_settings(message: Message):
    if not can_manage(message.from_user.id):
        await message.answer("⛔ Доступно только исполнителям и администраторам.")
        return
    await message.answer("🧼 *Настройки мойки*", parse_mode="Markdown", reply_markup=main_menu_kb())

async def show_wash_settings_menu(message: Message, bot: Bot):
    await message.answer("🧼 *Настройки мойки*", parse_mode="Markdown", reply_markup=main_menu_kb())

# ---------- Текущие настройки ----------
@router.callback_query(F.data == "wash:show")
async def show_settings(callback: CallbackQuery):
    service = get_or_create_wash_service()
    subtypes = get_subtypes()
    schedules = get_all_schedules()
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    status = "🟢 Работает" if service.is_active else "🔴 Не работает"
    text = f"🧼 *Мойка мотоциклов*\n\n"
    text += f"*Статус:* {status}\n"
    text += f"*Адрес:* {service.address or 'не указан'}\n"
    text += f"*Описание:* {service.description or 'не указано'}\n\n"
    text += f"*Стоимость:*\n"
    for s in subtypes:
        text += f"• {s.name}: {s.price} руб.\n"
    text += f"\n*Расписание:*\n"
    for i, sched in enumerate(schedules):
        day_name = days[i]
        if sched is None or not sched.is_working:
            text += f"{day_name}: выходной\n"
        else:
            hours_str = ", ".join(f"{h}:00" for h in sorted(sched.hours))
            text += f"{day_name}: {hours_str}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")]])
    if service.photos:
        photos = service.photos[:3]
        media = []
        for i, file_id in enumerate(photos):
            if i == 0:
                media.append(InputMediaPhoto(media=file_id, caption=text, parse_mode="Markdown"))
            else:
                media.append(InputMediaPhoto(media=file_id))
        try:
            await callback.message.delete()
            await callback.message.answer_media_group(media=media)
            await callback.message.answer("📋 Полный текст настроек выше", parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logger.error(f"Ошибка показа фото: {e}")
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "wash:menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text("🧼 *Настройки мойки*", parse_mode="Markdown", reply_markup=main_menu_kb())
    await callback.answer()

# ---------- Расписание ----------
@router.callback_query(F.data == "wash:schedule")
async def schedule_choose_day(callback: CallbackQuery):
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    buttons = []
    for i, day in enumerate(days):
        buttons.append([InlineKeyboardButton(text=day, callback_data=f"wash_day:{i}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите день недели:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("wash_day:"))
async def schedule_day_options(callback: CallbackQuery, state: FSMContext):
    day = int(callback.data.split(":")[1])
    await state.update_data(day=day)
    sched = get_all_schedules()[day]
    days_short = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    if sched is None:
        status = "выходной"
        hours = "нет"
    else:
        status = "рабочий" if sched.is_working else "выходной"
        hours = ", ".join(f"{h}:00" for h in sorted(sched.hours)) if sched.hours else "нет"
    text = f"*{days_short[day]}*\nСтатус: {status}\nЧасы: {hours}\n\nЧто хотите сделать?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переключить статус", callback_data="wash_toggle_status")],
        [InlineKeyboardButton(text="⏰ Изменить часы", callback_data="wash_edit_hours")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="wash:schedule")]
    ])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "wash_toggle_status")
async def toggle_status(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data.get("day")
    if day is None:
        await callback.answer("Ошибка: выберите день сначала.")
        return
    worker_id = get_fixed_worker_id()
    if not worker_id:
        await callback.answer("Исполнитель не найден. Добавьте через /add_worker")
        return
    current_schedules = get_all_schedules()
    sched = current_schedules[day]
    if sched is None:
        update_schedule(worker_id, day, is_working=True, hours=list(range(9, 21)), is_day_off=False)
    else:
        update_schedule(worker_id, day, is_working=not sched.is_working)
    regenerate_slots_for_worker(worker_id, days_ahead=7)
    await callback.answer("Статус изменён. Слоты обновлены.")
    await schedule_day_options(callback, state)


@router.callback_query(F.data == "wash_edit_hours")
async def edit_hours_prompt(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data.get("day")
    if day is None:
        await callback.answer("Ошибка: выберите день.")
        return
    current_schedules = get_all_schedules()
    sched = current_schedules[day]
    current_hours = sched.hours if sched and sched.is_working else []
    await state.update_data(selected_hours=current_hours.copy())
    await state.set_state(EditHoursState.selecting_hours)
    buttons = []
    for h in range(9, 21):
        mark = "✅" if h in current_hours else "⬜"
        buttons.append(InlineKeyboardButton(text=f"{mark} {h}:00", callback_data=f"wash_hour_toggle:{h}"))
    rows = [buttons[i:i+4] for i in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton(text="✅ Сохранить", callback_data="wash_save_hours")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash_cancel_hours")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await callback.message.edit_text("Выберите часы работы (нажмите на час, чтобы включить/выключить):", reply_markup=kb)
    except Exception as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise
    await callback.answer()

@router.callback_query(F.data.startswith("wash_hour_toggle:"))
async def toggle_hour_selection(callback: CallbackQuery, state: FSMContext):
    hour = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = data.get("selected_hours", [])
    if hour in selected:
        selected.remove(hour)
    else:
        selected.append(hour)
    await state.update_data(selected_hours=selected)
    new_kb = await build_hours_kb(state)
    try:
        await callback.message.edit_reply_markup(reply_markup=new_kb)
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()

@router.callback_query(F.data == "wash_save_hours")
async def save_hours_selection(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data.get("day")
    selected = data.get("selected_hours", [])
    if day is None:
        await callback.answer("Ошибка.")
        return
    selected.sort()
    update_schedule(day, hours=selected, is_working=True)
    worker_id = get_fixed_worker_id()
    if worker_id:
        regenerate_slots_for_worker(worker_id, days_ahead=7)
    await state.clear()
    await callback.answer("Расписание сохранено. Слоты обновлены.")
    await schedule_day_options(callback, state)

@router.callback_query(F.data == "wash_cancel_hours")
async def cancel_hours_selection(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    day = data.get("day")
    if day is None:
        await callback.answer("Ошибка.")
        return
    await state.clear()
    await schedule_day_options(callback, state)

async def build_hours_kb(state: FSMContext) -> InlineKeyboardMarkup:
    data = await state.get_data()
    selected = data.get("selected_hours", [])
    buttons = []
    for h in range(9, 21):
        mark = "✅" if h in selected else "⬜"
        buttons.append(InlineKeyboardButton(text=f"{mark} {h}:00", callback_data=f"wash_hour_toggle:{h}"))
    rows = [buttons[i:i+4] for i in range(0, len(buttons), 4)]
    rows.append([InlineKeyboardButton(text="✅ Сохранить", callback_data="wash_save_hours")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash_cancel_hours")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ---------- Стоимость мойки ----------
@router.callback_query(F.data == "wash:price")
async def price_menu(callback: CallbackQuery, state: FSMContext):
    subtypes = get_subtypes()
    if not subtypes:
        await callback.message.answer("Нет данных о стоимости.")
        return
    buttons = []
    for s in subtypes:
        buttons.append([InlineKeyboardButton(text=f"{s.name} ({s.price} руб.)", callback_data=f"wash_price_edit:{s.id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите тип мойки для изменения цены:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("wash_price_edit:"))
async def price_edit(callback: CallbackQuery, state: FSMContext):
    subtype_id = int(callback.data.split(":")[1])
    await state.update_data(subtype_id=subtype_id)
    await state.set_state(EditPriceState.waiting_price)
    await callback.message.edit_text("Введите новую цену (только рубли):")
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
    await cmd_wash_settings(message)

# ---------- Фотографии ----------
@router.callback_query(F.data == "wash:photos")
async def photos_menu(callback: CallbackQuery):
    service = get_or_create_wash_service()
    photos = service.photos
    text = f"🖼 *Фотографии мойки* ({len(photos)} шт.)\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фото", callback_data="wash:add_photo")],
        [InlineKeyboardButton(text="🗑 Удалить все фото", callback_data="wash:del_photos")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="wash:menu")]
    ])
    if photos:
        media = []
        for i, file_id in enumerate(photos[:3]):
            media.append(InputMediaPhoto(media=file_id, caption=text if i == 0 else ""))
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
    await callback.message.edit_text("Отправьте фотографию (можно несколько, отправляйте по одной).\nПосле каждой фото нажимайте /done, когда закончите.")
    await callback.answer()

@router.message(AddPhotoState.waiting_photo, F.photo)
async def photo_received(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ Фото добавлено. Всего в этой сессии: {len(photos)}. Отправьте ещё или нажмите /done для завершения.")

@router.message(Command("done"))
async def finish_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if photos:
        service = get_or_create_wash_service()
        all_photos = (service.photos or []) + photos
        if len(all_photos) > 10:
            all_photos = all_photos[:10]
        update_service(photos=all_photos)
        await message.answer(f"✅ Сохранено {len(photos)} новых фото. Всего фото: {len(all_photos)}.")
    else:
        await message.answer("Нет новых фото для сохранения.")
    await state.clear()
    await cmd_wash_settings(message)

@router.callback_query(F.data == "wash:del_photos")
async def delete_all_photos(callback: CallbackQuery):
    update_service(photos=[])
    await callback.message.edit_text("✅ Все фотографии удалены.")
    await asyncio.sleep(1)
    await photos_menu(callback)
    await callback.answer()

# ---------- Адрес мойки ----------
@router.callback_query(F.data == "wash:address")
async def ask_address(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditAddressState.waiting_address)
    await callback.message.edit_text("Введите новый адрес мойки:")
    await callback.answer()

@router.message(EditAddressState.waiting_address)
async def receive_address(message: Message, state: FSMContext):
    update_service(address=message.text.strip())
    await state.clear()
    await message.answer("✅ Адрес обновлён")
    await cmd_wash_settings(message)

# ---------- Описание мойки ----------
@router.callback_query(F.data == "wash:description")
async def ask_description(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditDescriptionState.waiting_description)
    await callback.message.edit_text("Введите новое описание мойки:")
    await callback.answer()

@router.message(EditDescriptionState.waiting_description)
async def receive_description(message: Message, state: FSMContext):
    update_service(description=message.text.strip())
    await state.clear()
    await message.answer("✅ Описание обновлено")
    await cmd_wash_settings(message)

# ---------- Управление исполнителями ----------
@router.callback_query(F.data == "wash:workers")
async def workers_list(callback: CallbackQuery):
    workers = get_all_workers()
    text = "👥 *Исполнители*\n\n"
    for w in workers:
        text += f"• {w.name} (ID {w.user_id})\n"
    text += "\n➕ Добавить: /add_worker ID Имя\n🗑 Удалить: /del_worker ID"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

@router.message(Command("add_worker"))
async def add_worker_cmd(message: Message):
    if not can_manage(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ Используйте: /add_worker <telegram_id> <имя>")
        return
    if not parts[1].isdigit():
        await message.answer("❌ ID должен быть числом.")
        return
    tid = int(parts[1])
    name = parts[2]
    add_worker(tid, name)
    await message.answer(f"✅ Исполнитель {name} (ID {tid}) добавлен.")

@router.message(Command("del_worker"))
async def del_worker_cmd(message: Message):
    if not can_manage(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❌ Используйте: /del_worker <telegram_id>")
        return
    tid = int(parts[1])
    delete_worker(tid)
    await message.answer(f"✅ Исполнитель с ID {tid} удалён.")

# ---------- Вкл/выкл мойку ----------
@router.callback_query(F.data == "wash:toggle_active")
async def toggle_active(callback: CallbackQuery):
    service = get_or_create_wash_service()
    new_status = not service.is_active
    update_service(is_active=new_status)
    await callback.answer(f"Мойка {'включена' if new_status else 'выключена'}", show_alert=True)
    await back_to_menu(callback)

# ---------- Назад в админ-панель ----------
@router.callback_query(F.data == "wash:back_to_admin")
async def back_to_admin_panel(callback: CallbackQuery):
    from handlers.admin import admin_panel_cmd
    await admin_panel_cmd(callback.message)
    await callback.answer()
