import json
import logging
import re
from pathlib import Path
from typing import Optional

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import GROUP_CHAT_ID
from database.engine import get_session
from database.models import User
from database.crud import delete_user_by_id

from utils.districts import MOSCOW_DISTRICTS
from keyboards.inline import get_districts_keyboard


logger = logging.getLogger(__name__)
router = Router(name="registration")

from keyboards.inline import get_districts_keyboard
from states.registration import RegistrationStates

# ---------- FSM для редактирования профиля ----------
class EditProfileStates(StatesGroup):
    choosing_field = State()
    editing_name = State()
    editing_birthday = State()
    editing_brand = State()
    editing_model = State()
    editing_district = State()

# ---------- Загрузка мотоциклов ----------
MOTORCYCLES_FILE = Path(__file__).resolve().parent.parent / "data" / "motorcycles.json"

def load_motorcycles() -> dict[str, list[str]]:
    if MOTORCYCLES_FILE.exists():
        with open(MOTORCYCLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "Honda": ["CBR600RR", "Africa Twin", "CB650R"],
        "Yamaha": ["R1", "R6", "MT-07", "MT-09"],
        "BMW": ["R1250GS", "S1000RR"],
        "Другое": ["Другая модель"],
    }

MOTORCYCLES = load_motorcycles()

# ---------- Вспомогательные функции БД ----------
def get_user(tg_id: int) -> Optional[User]:
    with get_session() as s:
        return s.query(User).filter(User.telegram_id == tg_id).first()

def upsert_user(tg_id: int, username: Optional[str], name: str, birthday: str, brand: str, model: str, district: Optional[str] = None):
    with get_session() as s:
        u = s.query(User).filter(User.telegram_id == tg_id).first()
        if u:
            u.username = username
            u.name = name
            u.birthday = birthday
            u.bike_brand = brand
            u.bike_model = model
            if district is not None:
                u.district = district
        else:
            s.add(User(
                telegram_id=tg_id,
                username=username,
                name=name,
                birthday=birthday,
                bike_brand=brand,
                bike_model=model,
                district=district,
            ))

# ---------- Клавиатуры ----------
def kb_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Начать регистрацию", callback_data="reg:start")]
    ])

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="reg:cancel")]
    ])

def kb_brands() -> InlineKeyboardMarkup:
    brands = list(MOTORCYCLES.keys())
    rows = []
    row = []
    for i, b in enumerate(brands, 1):
        row.append(InlineKeyboardButton(text=b, callback_data=f"reg:brand:{b}"))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="reg:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_models(brand: str) -> InlineKeyboardMarkup:
    models = MOTORCYCLES.get(brand, [])
    rows = []
    row = []
    for i, m in enumerate(models, 1):
        row.append(InlineKeyboardButton(text=m, callback_data=f"reg:model:{m}"))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="reg:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ---------- Регистрация ----------
async def _start_reg(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("Регистрация доступна только в личных сообщениях с ботом.")
        return
    if get_user(message.from_user.id):
        await message.answer("✅ Вы уже зарегистрированы.")
        await state.clear()
        return
    await state.set_state(RegistrationStates.waiting_name)
    await message.answer("Введите ваше имя:")

@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.startswith("/start register"):
        await _start_reg(message, state)
        return
    if get_user(message.from_user.id):
        await message.answer("Привет! ✅ Вы уже зарегистрированы.")
    else:
        await message.answer(
            "👋 Добро пожаловать!\nНажмите кнопку, чтобы зарегистрироваться.",
            reply_markup=kb_start(),
        )

@router.message(Command("register"))
async def register_cmd(message: Message, state: FSMContext):
    await _start_reg(message, state)

@router.callback_query(F.data == "reg:start")
async def reg_start_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _start_reg(callback.message, state)

@router.callback_query(F.data == "reg:cancel")
async def reg_cancel_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer("❌ Регистрация отменена.")

@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("Нет активного действия для отмены.")
        return
    await state.clear()
    await message.answer("❌ Отменено.")

@router.message(RegistrationStates.waiting_name)
async def name_step(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Введите ещё раз.")
        return
    await state.update_data(name=name)
    await state.set_state(RegistrationStates.waiting_birthday)
    await message.answer("🎂 Дата рождения в формате ДД.ММ (пример: 17.08)")

@router.message(RegistrationStates.waiting_birthday)
async def birthday_step(message: Message, state: FSMContext):
    birthday = (message.text or "").strip()
    if not re.match(r"^\d{2}\.\d{2}$", birthday):
        await message.answer("❌ Неверный формат. Нужно ДД.ММ")
        return
    d, m = map(int, birthday.split('.'))
    if not (1 <= d <= 31 and 1 <= m <= 12):
        await message.answer("❌ Некорректная дата.")
        return
    await state.update_data(birthday=birthday)
    await state.set_state(RegistrationStates.waiting_brand)
    await message.answer("🏍 Выберите марку:", reply_markup=kb_brands())

@router.callback_query(RegistrationStates.waiting_brand, F.data.startswith("reg:brand:"))
async def brand_step(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    brand = callback.data.split(":", 2)[2]
    await state.update_data(brand=brand)
    await state.set_state(RegistrationStates.waiting_model)
    await callback.message.answer("Выберите модель:", reply_markup=kb_models(brand))


@router.callback_query(RegistrationStates.waiting_model, F.data.startswith("reg:model:"))
async def model_step(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    model = callback.data.split(":", 2)[2]
    await state.update_data(model=model)
    await state.set_state(RegistrationStates.waiting_district)
    await callback.message.answer(
        "Выберите округ Москвы, в котором вы обычно катаетесь:",
        reply_markup=get_districts_keyboard()
    )

@router.callback_query(RegistrationStates.waiting_district, F.data.startswith("district:"))
async def district_step(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    district = callback.data.split(":", 1)[1]
    data = await state.get_data()
    # Сохраняем все данные, включая округ
    upsert_user(
        tg_id=callback.from_user.id,
        username=callback.from_user.username,
        name=data["name"],
        birthday=data["birthday"],
        brand=data["brand"],
        model=data["model"],
        district=district
    )
    await state.clear()
    await callback.message.answer(
        f"✅ Готово! Вы зарегистрированы.\n\n"
        f"Имя: {data['name']}\n"
        f"ДР: {data['birthday']}\n"
        f"Мото: {data['brand']} {data['model']}\n"
        f"Округ: {district}"
    )
    # Отправка уведомления в группу (опционально)
    if GROUP_CHAT_ID:
        try:
            await callback.bot.send_message(
                GROUP_CHAT_ID,
                f"👋 Новый участник: {data['name']} — {data['brand']} {data['model']}"
            )
        except Exception as e:
            logger.warning(f"Failed to notify group: {e}")




@router.message(RegistrationStates.waiting_year)
async def year_step(message: Message, state: FSMContext):
    year_text = (message.text or "").strip()
    # Год не сохраняем (можно игнорировать)
    data = await state.get_data()
    upsert_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        name=data["name"],
        birthday=data["birthday"],
        brand=data["brand"],
        model=data["model"],
        district=data.get("district")
    )
    await state.clear()
    await message.answer(
        f"✅ Готово! Вы зарегистрированы.\n\n"
        f"Имя: {data['name']}\n"
        f"ДР: {data['birthday']}\n"
        f"Мото: {data['brand']} {data['model']}"
        + (f"\nОкруг: {data.get('district', 'не указан')}" if data.get('district') else "")
    )
    if GROUP_CHAT_ID:
        try:
            await message.bot.send_message(
                GROUP_CHAT_ID,
                f"👋 Новый участник: {data['name']} — {data['brand']} {data['model']}"
            )
        except Exception as e:
            logger.warning(f"Failed to notify group: {e}")


# ---------- Профиль ----------
@router.message(Command("my_profile"))
async def my_profile_cmd(message: Message):
    if message.chat.type != "private":
        await message.answer("Доступно только в ЛС.")
        return
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Вы не зарегистрированы.")
            return
        text = (
            f"📝 *Ваша анкета:*\n\n"
            f"🆔 Telegram ID: `{user.telegram_id}`\n"
            f"👤 Имя: {user.name}\n"
            f"🎂 Дата рождения: {user.birthday or 'не указана'}\n"
            f"🏍 Мотоцикл: {user.bike_brand} {user.bike_model or ''}\n"
            f"🗺 Округ: {user.district or 'не указан'}\n"
            f"📅 Зарегистрирован: {user.registered_at.strftime('%d.%m.%Y %H:%M') if user.registered_at else 'неизвестно'}"
        )
        await message.answer(text, parse_mode="Markdown")

# ---------- Редактирование профиля (только имя, дата, марка, модель) ----------
@router.message(Command("edit_my_profile"))
async def edit_profile_cmd(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("Доступно только в ЛС.")
        return
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer("❌ Вы не зарегистрированы.")
            return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Имя", callback_data="edit:name")],
        [InlineKeyboardButton(text="🎂 Дата рождения", callback_data="edit:birthday")],
        [InlineKeyboardButton(text="🏍 Марка", callback_data="edit:brand")],
        [InlineKeyboardButton(text="🔧 Модель", callback_data="edit:model")],
        [InlineKeyboardButton(text="🗺 Округ", callback_data="edit:district")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit:cancel")]
    ])
    await state.set_state(EditProfileStates.choosing_field)
    await message.answer("Что хотите изменить?", reply_markup=kb)

@router.callback_query(EditProfileStates.choosing_field, F.data.startswith("edit:"))
async def edit_choose_field(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    action = callback.data.split(":")[1]
    if action == "cancel":
        await state.clear()
        await callback.message.answer("Редактирование отменено.")
        await callback.message.edit_reply_markup(reply_markup=None)
        return
    if action == "name":
        await state.set_state(EditProfileStates.editing_name)
        await callback.message.answer("Введите новое имя:")
    elif action == "birthday":
        await state.set_state(EditProfileStates.editing_birthday)
        await callback.message.answer("Введите новую дату (ДД.ММ):")
    elif action == "brand":
        await state.set_state(EditProfileStates.editing_brand)
        await callback.message.answer("Выберите новую марку:", reply_markup=kb_brands())
    
    elif action == "district":
        await state.set_state(EditProfileStates.editing_district)
        await callback.message.answer(
            "Выберите новый округ Москвы:",
            reply_markup=get_districts_keyboard()
    )
    elif action == "model":
        brand = None
        with get_session() as session:
            user = session.query(User).filter(User.telegram_id == callback.from_user.id).first()
            if user:
                brand = user.bike_brand
        if brand:
            await state.update_data(edit_brand=brand)
            await state.set_state(EditProfileStates.editing_model)
            await callback.message.answer("Выберите новую модель:", reply_markup=kb_models(brand))
        else:
            await callback.message.answer("Сначала укажите марку мотоцикла.")
            await state.clear()

@router.message(EditProfileStates.editing_name)
async def edit_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Слишком короткое имя.")
        return
    with get_session() as s:
        user = s.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            user.name = name
            s.commit()
    await state.clear()
    await message.answer(f"✅ Имя обновлено на {name}.")

@router.message(EditProfileStates.editing_birthday)
async def edit_birthday(message: Message, state: FSMContext):
    birthday = message.text.strip()
    if not re.match(r"^\d{2}\.\d{2}$", birthday):
        await message.answer("❌ Неверный формат. Нужно ДД.ММ")
        return
    d, m = map(int, birthday.split('.'))
    if not (1 <= d <= 31 and 1 <= m <= 12):
        await message.answer("❌ Некорректная дата.")
        return
    with get_session() as s:
        user = s.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            user.birthday = birthday
            s.commit()
    await state.clear()
    await message.answer(f"✅ Дата рождения обновлена на {birthday}.")

@router.callback_query(EditProfileStates.editing_brand, F.data.startswith("reg:brand:"))
async def edit_brand(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    brand = callback.data.split(":", 2)[2]
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if user:
            user.bike_brand = brand
            user.bike_model = None
            session.commit()
            await callback.message.answer(f"✅ Марка обновлена на {brand}. Теперь выберите модель:", reply_markup=kb_models(brand))
            await state.set_state(EditProfileStates.editing_model)
            await state.update_data(edit_brand=brand)
        else:
            await callback.message.answer("❌ Пользователь не найден.")
            await state.clear()

@router.callback_query(EditProfileStates.editing_model, F.data.startswith("reg:model:"))
async def edit_model(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    model = callback.data.split(":", 2)[2]
    data = await state.get_data()
    brand = data.get("edit_brand")
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if user:
            if brand:
                user.bike_brand = brand
            user.bike_model = model
            session.commit()
    await state.clear()
    await callback.message.answer(f"✅ Модель обновлена на {model}.")

@router.message(EditProfileStates.editing_model)
async def edit_model_text(message: Message, state: FSMContext):
    model = message.text.strip()
    if len(model) < 1:
        await message.answer("Введите название модели.")
        return
    data = await state.get_data()
    brand = data.get("edit_brand")
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == message.from_user.id).first()
        if user:
            if brand:
                user.bike_brand = brand
            user.bike_model = model
            session.commit()
    await state.clear()
    await message.answer(f"✅ Модель обновлена на {model}.")

# ---------- Удаление профиля ----------
@router.message(Command("delete_my_profile"))
async def delete_my_profile_cmd(message: Message):
    await delete_profile_cmd(message)

@router.message(Command("delete_profile"))
async def delete_profile_cmd(message: Message):
    if message.chat.type != "private":
        await message.answer("Доступно только в ЛС.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_delete"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")]
    ])
    await message.answer("⚠️ Вы уверены? Это необратимо.", reply_markup=kb)

@router.callback_query(F.data == "confirm_delete")
async def confirm_delete_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.answer()
    if delete_user_by_id(user_id):
        await callback.message.edit_text("🗑 Ваша анкета удалена.")
    else:
        await callback.message.edit_text("❌ Анкета не найдена.")
    await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data == "cancel_delete")
async def cancel_delete_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("✅ Удаление отменено.")
    await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(EditProfileStates.editing_district, F.data.startswith("district:"))
async def edit_district(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    district = callback.data.split(":", 1)[1]
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if user:
            user.district = district
            session.commit()
    await state.clear()
    await callback.message.answer(f"✅ Округ обновлён на {district}.")