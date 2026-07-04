import logging
import html
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta, date
from database.wash_crud import (
    get_or_create_wash_service, get_available_slots,
    generate_slots_for_range, create_booking_with_status,
    confirm_booking, reject_booking, get_worker_by_telegram_id,
    get_subtypes, get_subtype_by_id, get_all_schedules
)
from database.crud import get_user_by_telegram_id, get_user_bike_details
from config import ADMIN_IDS

logger = logging.getLogger(__name__)
router = Router(name="wash_booking")

WORKER_TELEGRAM_ID = 194851131
OWNER_ID = ADMIN_IDS[0] if ADMIN_IDS else None

class BookingStates(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    choosing_subtype = State()
    confirming = State()

async def get_main_worker():
    worker = get_worker_by_telegram_id(WORKER_TELEGRAM_ID)
    if not worker:
        logger.error(f"Исполнитель с Telegram ID {WORKER_TELEGRAM_ID} не найден")
        return None
    return worker

@router.message(Command("wash"))
async def cmd_wash(message: Message, state: FSMContext):
    service = get_or_create_wash_service()
    subtypes = get_subtypes()
    schedules = get_all_schedules()
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    status = "🟢 Работает" if service.is_active else "🔴 Не работает"
    text = f"🧼 <b>Мойка мотоциклов</b>\n\n"
    text += f"<b>Статус:</b> {status}\n"
    text += f"<b>Адрес:</b> {html.escape(service.address or 'не указан')}\n"
    text += f"<b>Описание:</b> {html.escape(service.description or 'не указано')}\n\n"
    text += f"<b>Стоимость:</b>\n"
    for s in subtypes:
        text += f"• {html.escape(s.name)}: {s.price} руб.\n"
    text += f"\n<b>Расписание:</b>\n"
    has_schedule = False
    for i, sched in enumerate(schedules):
        day_name = days[i]
        if not sched or not sched.is_working:
            text += f"{day_name}: выходной\n"
        else:
            has_schedule = True
            hours_str = ", ".join(f"{h}:00" for h in sorted(sched.hours))
            text += f"{day_name}: {hours_str}\n"
    if not has_schedule:
        text += "⚠️ Расписание не задано. Запись невозможна.\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Записаться", callback_data="wash_start")]
    ])
    if service.photos:
        photos = service.photos[:3]
        media = []
        for i, file_id in enumerate(photos):
            if i == 0:
                media.append(InputMediaPhoto(media=file_id, caption=text, parse_mode="HTML"))
            else:
                media.append(InputMediaPhoto(media=file_id))
        try:
            await message.answer_media_group(media=media)
            await message.answer("👇 Для записи нажмите кнопку:", reply_markup=kb)
        except Exception as e:
            logger.error(f"Ошибка показа фото: {e}")
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "wash_start")
async def start_booking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    worker = await get_main_worker()
    if not worker:
        await callback.message.answer("Нет исполнителя. Сообщите администратору.")
        return

    # Проверяем наличие расписания
    schedules = get_all_schedules()
    has_working = any(sched and sched.is_working and sched.hours for sched in schedules)
    if not has_working:
        await callback.message.edit_text("🧼 Расписание мойки не задано администратором. Запись временно недоступна.")
        await state.clear()
        return
    await state.update_data(worker_id=worker.id)
    
    start_date = date.today()
    from database.engine import get_session
    from database.models import TimeSlot
    
    # 1. Удаляем слоты для выходных дней
    for i in range(7):
        target_date = start_date + timedelta(days=i)
        dow = target_date.weekday()
        sched = schedules[dow] if dow < len(schedules) else None
        if not sched or not sched.is_working:
            with get_session() as session:
                session.query(TimeSlot).filter(
                    TimeSlot.worker_id == worker.id,
                    TimeSlot.date == target_date
                ).delete()
                session.commit()
    
    # 2. Генерируем слоты только для рабочих дней
    for i in range(7):
        target_date = start_date + timedelta(days=i)
        dow = target_date.weekday()
        sched = schedules[dow] if dow < len(schedules) else None
        if sched and sched.is_working:
            generate_slots_for_range(worker.id, target_date, days=1)
            # После цикла generate_slots_for_range
            logger.error(f"DEBUG: worker_id={worker.id}, schedules={[(i, sched.is_working, sched.hours) for i, sched in enumerate(schedules) if sched]}") 
            for i in range(7):
                  day = start_date + timedelta(days=i)
                  slots = get_available_slots(worker.id, day)
                  logger.error(f"DEBUG: day={day}, slots={len(slots)}")    
    # 3. Собираем доступные даты (где есть свободные слоты)
    available_dates = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        slots = get_available_slots(worker.id, day)
        if slots:
            available_dates.append(day)
    
    if not available_dates:
        await callback.message.edit_text("🧼 На ближайшие 7 дней нет свободных слотов.")
        await state.clear()
        return
    
    await state.set_state(BookingStates.choosing_date)
    buttons = []
    for d in available_dates:
        buttons.append([InlineKeyboardButton(text=d.strftime("%d.%m.%Y"), callback_data=f"wash_date:{d.isoformat()}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="wash_cancel")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("📅 Выберите дату:", reply_markup=kb)


@router.callback_query(BookingStates.choosing_date, F.data.startswith("wash_date:"))
async def choose_date(callback: CallbackQuery, state: FSMContext):
    selected_date = date.fromisoformat(callback.data.split(":")[1])
    await state.update_data(date=selected_date)
    data = await state.get_data()
    worker_id = data["worker_id"]
    slots = get_available_slots(worker_id, selected_date)
    if not slots:
        await callback.answer("Извините, слоты на эту дату закончились.", show_alert=True)
        await state.set_state(BookingStates.choosing_date)
        await start_booking(callback, state)
        return
    await state.set_state(BookingStates.choosing_time)
    buttons = []
    for slot in slots:
        free = 2 - slot.booked_bikes
        buttons.append([InlineKeyboardButton(text=f"{slot.hour}:00 (свободно {free} мест)", callback_data=f"wash_time:{slot.id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash_back_to_dates")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="wash_cancel")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("⏰ Выберите время:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "wash_back_to_dates")
async def back_to_dates(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_date)
    await start_booking(callback, state)

@router.callback_query(BookingStates.choosing_time, F.data.startswith("wash_time:"))
async def choose_time(callback: CallbackQuery, state: FSMContext):
    slot_id = int(callback.data.split(":")[1])
    await state.update_data(slot_id=slot_id)
    subtypes = get_subtypes()
    if not subtypes:
        await callback.answer("Ошибка: нет доступных услуг.", show_alert=True)
        return
    await state.set_state(BookingStates.choosing_subtype)
    buttons = []
    for sub in subtypes:
        buttons.append([InlineKeyboardButton(text=f"{sub.name} — {sub.price} руб.", callback_data=f"wash_subtype:{sub.id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash_back_to_time")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="wash_cancel")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("🧼 Выберите тип мойки:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "wash_back_to_time")
async def back_to_time(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_time)
    data = await state.get_data()
    selected_date = data.get("date")
    worker_id = data.get("worker_id")
    if not selected_date or not worker_id:
        await callback.answer("Ошибка, начните сначала.")
        await state.clear()
        return
    slots = get_available_slots(worker_id, selected_date)
    if not slots:
        await callback.answer("Слоты закончились.", show_alert=True)
        await state.clear()
        return
    buttons = []
    for slot in slots:
        free = 2 - slot.booked_bikes
        buttons.append([InlineKeyboardButton(text=f"{slot.hour}:00 (свободно {free} мест)", callback_data=f"wash_time:{slot.id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wash_back_to_dates")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="wash_cancel")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("⏰ Выберите время:", reply_markup=kb)
    await callback.answer()

@router.callback_query(BookingStates.choosing_subtype, F.data.startswith("wash_subtype:"))
async def choose_subtype(callback: CallbackQuery, state: FSMContext):
    subtype_id = int(callback.data.split(":")[1])
    await state.update_data(subtype_id=subtype_id)
    data = await state.get_data()
    worker_id = data["worker_id"]
    selected_date = data["date"]
    slot_id = data["slot_id"]
    user_id = callback.from_user.id
    user = get_user_by_telegram_id(user_id)
    if not user:
        await callback.message.edit_text("❌ Вы не зарегистрированы. Используйте /register.")
        await state.clear()
        return
    bike_brand, bike_model = get_user_bike_details(user_id)
    bike = f"{bike_brand} {bike_model}".strip() or "не указан"
    username = f"@{user.username}" if user.username else user.name
    from database.models import WashWorker
    from database.engine import get_session
    with get_session() as session:
        worker = session.query(WashWorker).filter(WashWorker.id == worker_id).first()
    if not worker:
        await callback.answer("Ошибка: исполнитель не найден.", show_alert=True)
        await state.clear()
        return
    slot = next((s for s in get_available_slots(worker_id, selected_date) if s.id == slot_id), None)
    if not slot:
        await callback.answer("Ошибка: слот не найден.", show_alert=True)
        await state.clear()
        return
    subtype = get_subtype_by_id(subtype_id)
    if not subtype:
        await callback.answer("Ошибка: услуга не найдена.", show_alert=True)
        return
    text = f"📝 <b>Подтверждение записи</b>\n\n"
    text += f"🧼 Мастер: {html.escape(worker.name)}\n"
    text += f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
    text += f"⏰ Время: {slot.hour}:00\n"
    text += f"🧼 Услуга: {html.escape(subtype.name)}\n"
    text += f"💰 Цена: {subtype.price} руб.\n"
    text += f"👤 Имя: {html.escape(user.name)}\n"
    text += f"🏍 Мотоцикл: {html.escape(bike)}\n"
    text += f"🔗 Ник: {html.escape(username)}\n\n"
    text += "Всё верно?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="wash_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="wash_cancel")]
    ])
    await state.set_state(BookingStates.confirming)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "wash_confirm")
async def confirm_booking_cb(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id
    slot_id = data.get("slot_id")
    subtype_id = data.get("subtype_id")
    if not slot_id or not subtype_id:
        await callback.answer("Ошибка. Попробуйте заново.")
        await state.clear()
        return
    booking = create_booking_with_status(user_id, slot_id, subtype_id, bikes_count=1, status="pending")
    if not booking:
        await callback.message.edit_text("❌ Не удалось записаться. Возможно, слот уже занят.")
        await state.clear()
        return
    user = get_user_by_telegram_id(user_id)
    bike_brand, bike_model = get_user_bike_details(user_id)
    bike = f"{bike_brand} {bike_model}".strip() or "не указан"
    username = f"@{user.username}" if user.username else user.name
    date_str = data["date"].strftime("%d.%m.%Y")
    from database.engine import get_session
    from database.models import TimeSlot
    with get_session() as session:
        slot = session.query(TimeSlot).filter(TimeSlot.id == slot_id).first()
        hour = slot.hour if slot else "??"
    subtype = get_subtype_by_id(subtype_id)
    subtype_name = subtype.name if subtype else "неизвестно"
    subtype_price = subtype.price if subtype else 0
    worker = await get_main_worker()
    if worker:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"wash_accept:{booking.id}")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wash_reject:{booking.id}")]
            ])
            # Отправляем уведомление исполнителю, используя HTML
            await callback.bot.send_message(
                worker.user_id,
                f"🧼 <b>Новая запись на мойку!</b>\n\n"
                f"👤 Имя: {html.escape(user.name)}\n"
                f"🔗 Ник: {html.escape(username)}\n"
                f"🏍 Мотоцикл: {html.escape(bike)}\n"
                f"📅 Дата: {html.escape(date_str)}\n"
                f"⏰ Время: {hour}:00\n"
                f"🧼 Услуга: {html.escape(subtype_name)}\n"
                f"💰 Цена: {subtype_price} руб.\n\n"
                f"Подтвердите или отклоните запись:",
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление исполнителю {worker.user_id}: {e}")
    await callback.message.edit_text("✅ Запись отправлена на подтверждение мастеру. Ожидайте ответа.")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("wash_accept:"))
async def accept_booking(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    if confirm_booking(booking_id):
        from database.engine import get_session
        from database.models import Booking, TimeSlot, WashWorker, WashSubtype
        with get_session() as session:
            booking = session.query(Booking).filter(Booking.id == booking_id).first()
            if not booking:
                await callback.answer("Бронирование не найдено.")
                return
            slot = session.query(TimeSlot).filter(TimeSlot.id == booking.slot_id).first()
            worker = session.query(WashWorker).filter(WashWorker.id == slot.worker_id).first()
            subtype = session.query(WashSubtype).filter(WashSubtype.id == booking.subtype_id).first()
            user_id = booking.user_id
        user = get_user_by_telegram_id(user_id)
        if user:
            await callback.bot.send_message(
                user_id,
                f"✅ Ваша запись на мойку подтверждена!\n"
                f"Мастер: {worker.name}\n"
                f"Дата: {slot.date.strftime('%d.%m.%Y')}\n"
                f"Время: {slot.hour}:00\n"
                f"Услуга: {subtype.name if subtype else 'стандартная'}\n"
                f"Цена: {subtype.price if subtype else 'уточните'} руб.\n\n"
                f"Ждём вас!"
            )
        if OWNER_ID:
            # Используем HTML
            await callback.bot.send_message(
                OWNER_ID,
                f"✅ <b>Запись подтверждена исполнителем!</b>\n\n"
                f"👤 Клиент: {html.escape(user.name if user else 'Неизвестный')} (@{html.escape(user.username if user else 'нет')})\n"
                f"🏍 Мотоцикл: {html.escape(get_user_bike_details(user_id)[0])} {html.escape(get_user_bike_details(user_id)[1])}\n"
                f"📅 Дата: {slot.date.strftime('%d.%m.%Y')}\n"
                f"⏰ Время: {slot.hour}:00\n"
                f"🧼 Услуга: {html.escape(subtype.name if subtype else 'стандартная')}\n"
                f"💰 Цена: {subtype.price if subtype else 0} руб.\n\n"
                f"Запись подтверждена, клиент договорился.",
                parse_mode="HTML"
            )
        if worker:
            await callback.bot.send_message(
                worker.user_id,
                f"✅ <b>Запись подтверждена вами!</b>\n\n"
                f"👤 Клиент: {html.escape(user.name if user else 'Неизвестный')} (@{html.escape(user.username if user else 'нет')})\n"
                f"🏍 Мотоцикл: {html.escape(get_user_bike_details(user_id)[0])} {html.escape(get_user_bike_details(user_id)[1])}\n"
                f"📅 Дата: {slot.date.strftime('%d.%m.%Y')}\n"
                f"⏰ Время: {slot.hour}:00\n"
                f"🧼 Услуга: {html.escape(subtype.name if subtype else 'стандартная')}\n"
                f"💰 Цена: {subtype.price if subtype else 0} руб.",
                parse_mode="HTML"
            )

        await callback.message.edit_text("✅ Запись подтверждена.")
    else:
        await callback.message.edit_text("❌ Не удалось подтвердить запись (возможно, её уже отклонили).")
    await callback.answer()

@router.callback_query(F.data.startswith("wash_reject:"))
async def reject_booking_cb(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])
    if reject_booking(booking_id):
        from database.engine import get_session
        from database.models import Booking
        with get_session() as session:
            booking = session.query(Booking).filter(Booking.id == booking_id).first()
            if booking:
                user_id = booking.user_id
        await callback.bot.send_message(
            user_id,
            f"❌ К сожалению, мастер отклонил вашу запись. Попробуйте выбрать другое время."
        )
        if OWNER_ID:
            await callback.bot.send_message(
                OWNER_ID,
                f"❌ <b>Запись отклонена исполнителем</b>\n\nБронирование #{booking_id} отклонено.",
                parse_mode="HTML"
            )
        await callback.message.edit_text("❌ Запись отклонена.")
    else:
        await callback.message.edit_text("❌ Не удалось отклонить запись.")
    await callback.answer()

@router.callback_query(F.data == "wash_cancel")
async def cancel_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Запись отменена.")
    await callback.answer()
