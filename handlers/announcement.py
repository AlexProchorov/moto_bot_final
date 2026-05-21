import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, FSInputFile, URLInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
from config import GROUP_CHAT_ID, ADMIN_IDS
from database.engine import get_session
from database.models import User

logger = logging.getLogger(__name__)
router = Router(name="announcement")

def is_admin(uid: int) -> bool:
    return uid in [int(a) for a in ADMIN_IDS]

class AnnounceStates(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    waiting_confirm = State()

# Временное хранение данных анонса
user_announce_data = {}

@router.message(Command("announce"))
async def cmd_announce(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для администраторов.")
        return
    await state.set_state(AnnounceStates.waiting_text)
    await message.answer("📢 Введите текст анонса:")

@router.message(AnnounceStates.waiting_text)
async def announce_text(message: Message, state: FSMContext):
    await state.update_data(text=message.html_text, entities=message.entities)
    await state.set_state(AnnounceStates.waiting_photo)
    # Кнопка "Пропустить фото"
    kb = InlineKeyboardBuilder()
    kb.button(text="⏩ Пропустить фото", callback_data="announce_skip_photo")
    await message.answer(
        "🖼 Теперь отправьте фото (можно одно).\nИли нажмите «Пропустить фото».",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "announce_skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photo_file_id=None, photo_type=None)
    await callback.answer()
    await state.set_state(AnnounceStates.waiting_confirm)
    await show_preview(callback.message, state)

@router.message(AnnounceStates.waiting_photo, F.photo)
async def announce_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]  # лучшее качество
    await state.update_data(photo_file_id=photo.file_id, photo_type="file_id")
    await state.set_state(AnnounceStates.waiting_confirm)
    await show_preview(message, state)

@router.message(AnnounceStates.waiting_photo)
async def announce_photo_invalid(message: Message):
    await message.answer("❌ Пожалуйста, отправьте фото или нажмите «Пропустить фото».")

async def show_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    text = data.get("text", "")
    entities = data.get("entities", None)
    photo_file_id = data.get("photo_file_id")

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить анонс", callback_data="announce_send")
    kb.button(text="❌ Отмена", callback_data="announce_cancel")

    if photo_file_id:
        await message.answer_photo(
            photo=photo_file_id,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
    else:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
    await message.answer("👇 Подтвердите отправку анонса:")

@router.callback_query(F.data == "announce_send")
async def send_announce(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Начинаем рассылку...")
    data = await state.get_data()
    text = data.get("text", "")
    entities = data.get("entities", None)
    photo_file_id = data.get("photo_file_id")
    photo_type = data.get("photo_type")

    # Получаем всех пользователей из БД
    with get_session() as session:
        users = session.query(User).all()

    success_count = 0
    fail_count = 0

    # Рассылка в ЛС
    for user in users:
        try:
            if photo_file_id:
                await callback.bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=photo_file_id,
                    caption=text,
                    parse_mode="HTML"
                )
            else:
                await callback.bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML"
                )
            success_count += 1
            await asyncio.sleep(0.05)  # защита от флуда
        except Exception as e:
            logger.error(f"Не удалось отправить анонс пользователю {user.telegram_id}: {e}")
            fail_count += 1

    # Отправка в общий чат
    try:
        if photo_file_id:
            await callback.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=photo_file_id,
                caption=text,
                parse_mode="HTML"
            )
        else:
            await callback.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=text,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Не удалось отправить анонс в группу: {e}")

    # Итоговое сообщение админу
    await callback.message.answer(
        f"✅ Анонс отправлен!\n"
        f"📨 В ЛС: {success_count} пользователей\n"
        f"❌ Ошибок: {fail_count}\n"
        f"📢 Группа: анонс опубликован."
    )
    await state.clear()

@router.callback_query(F.data == "announce_cancel")
async def cancel_announce(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("❌ Анонс отменён.")
    await callback.answer()