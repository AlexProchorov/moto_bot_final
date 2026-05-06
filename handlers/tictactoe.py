import logging
import random
from datetime import datetime
from typing import Optional
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import GROUP_CHAT_ID, ADMIN_IDS
from database.crud import (
    user_exists, get_active_game, create_game, save_move, finish_game,
    get_player_stats, auto_abandon_stale_game
)
from database.engine import get_session
from database.models import User

logger = logging.getLogger(__name__)
router = Router(name="tictactoe")

class ChallengeStates(StatesGroup):
    waiting_challenge = State()

# Временное хранилище вызовов
challenges = {}

# ---------- Команда вызова ----------
@router.message(Command("tictactoe"))
async def tictactoe_cmd(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("❌ Игра доступна только в личных сообщениях с ботом.")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Используйте: `/tictactoe @username` или `/tictactoe <user_id>`", parse_mode="Markdown")
        return
    target = args[1].strip()
    # Определяем ID противника
    if target.startswith('@'):
        username = target[1:]
        with get_session() as session:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                await message.answer(f"❌ Пользователь @{username} не зарегистрирован в боте.")
                return
            opponent_id = user.telegram_id
    else:
        if not target.isdigit():
            await message.answer("❌ Введите корректный ID или @username.")
            return
        opponent_id = int(target)
        if not user_exists(opponent_id):
            await message.answer(f"❌ Пользователь с ID {opponent_id} не зарегистрирован.")
            return

    challenger_id = message.from_user.id
    if challenger_id == opponent_id:
        await message.answer("❌ Нельзя играть с самим собой.")
        return

    # Проверка на активные или зависшие игры
    if get_active_game(challenger_id) or get_active_game(opponent_id):
        # Если есть зависшая игра у вызывающего – завершаем
        if auto_abandon_stale_game(challenger_id):
            await message.answer("⚠️ Ваша предыдущая игра была зависшей и завершена. Теперь можно создать новую.")
        elif auto_abandon_stale_game(opponent_id):
            await message.answer("⚠️ У противника была зависшая игра. Она завершена. Повторите вызов.")
        else:
            await message.answer("❌ Один из игроков уже участвует в активной игре. Завершите её сначала (можно через /ttt_abandon).")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять вызов", callback_data=f"ttt_accept:{challenger_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"ttt_decline:{challenger_id}")]
    ])
    challenger_name = message.from_user.first_name
    try:
        await message.bot.send_message(opponent_id, f"🎮 Игрок {challenger_name} вызывает вас на партию в крестики-нолики!", reply_markup=kb)
        await message.answer("✅ Вызов отправлен. Ожидайте ответа.")
        challenges[challenger_id] = {"opponent_id": opponent_id, "timestamp": datetime.now()}
    except Exception as e:
        logger.error(f"Не удалось отправить вызов: {e}")
        await message.answer("❌ Не удалось отправить вызов. Возможно, пользователь не начал диалог с ботом.")

# ---------- Принятие/отклонение вызова ----------
@router.callback_query(F.data.startswith("ttt_accept:"))
async def accept_challenge(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    challenger_id = int(callback.data.split(":")[1])
    opponent_id = callback.from_user.id
    if get_active_game(challenger_id) or get_active_game(opponent_id):
        await callback.message.edit_text("❌ Один из игроков уже в игре. Невозможно начать.")
        return
    try:
        topic_name = f"🎮 Крестики-нолики: {callback.from_user.first_name} vs {callback.message.from_user.first_name}"
        topic = await bot.create_forum_topic(GROUP_CHAT_ID, name=topic_name)
        thread_id = topic.message_thread_id
    except Exception as e:
        logger.error(f"Не удалось создать тему: {e}")
        await callback.message.edit_text("❌ Не удалось создать игровую тему. Бот должен быть администратором группы и включены темы.")
        return
    first = random.choice([challenger_id, opponent_id])
    game = create_game(GROUP_CHAT_ID, thread_id, challenger_id, opponent_id, first)
    await send_game_board(bot, game.id)
    await bot.send_message(challenger_id, f"🎮 Игра началась! Ваш ход {'первым' if challenger_id == first else 'вторым'}. Следите за игровой темой.")
    await bot.send_message(opponent_id, f"🎮 Игра началась! Ваш ход {'первым' if opponent_id == first else 'вторым'}. Следите за игровой темой.")
    await callback.message.edit_text("✅ Вы приняли вызов! Игра началась.")

@router.callback_query(F.data.startswith("ttt_decline:"))
async def decline_challenge(callback: CallbackQuery):
    await callback.answer()
    challenger_id = int(callback.data.split(":")[1])
    await callback.message.edit_text("❌ Вы отклонили вызов.")
    await callback.bot.send_message(challenger_id, "❌ Противник отклонил вызов.")

# ---------- Отправка/обновление игрового поля ----------
async def send_game_board(bot: Bot, game_id: int):
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game:
            return
        board = game.board
        turn_id = game.turn_id
        player_x_id = game.player_x_id
        player_o_id = game.player_o_id
        user_x = session.query(User).filter(User.telegram_id == player_x_id).first()
        user_o = session.query(User).filter(User.telegram_id == player_o_id).first()
        name_x = user_x.name if user_x else str(player_x_id)
        name_o = user_o.name if user_o else str(player_o_id)
        stats_x = get_player_stats(player_x_id)
        stats_o = get_player_stats(player_o_id)
        text = (
            f"🎮 *Крестики-нолики*\n"
            f"❌ {name_x} (X)  |  ⭕ {name_o} (O)\n"
            f"📊 {name_x}: {stats_x['games_won']} побед | {name_o}: {stats_o['games_won']} побед\n"
            f"Сейчас ходит: {'❌' if turn_id == player_x_id else '⭕'}\n\n"
        )
        keyboard = []
        for i in range(0, 9, 3):
            row = []
            for j in range(3):
                idx = i + j
                cell = board[idx]
                if cell == 'X':
                    row.append(InlineKeyboardButton(text="❌", callback_data="ttt_noop"))
                elif cell == 'O':
                    row.append(InlineKeyboardButton(text="⭕", callback_data="ttt_noop"))
                else:
                    row.append(InlineKeyboardButton(text=str(idx+1), callback_data=f"ttt_move:{game_id}:{idx}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f"ttt_surrender:{game_id}")])
        keyboard.append([InlineKeyboardButton(text="🚪 Завершить игру", callback_data=f"ttt_end:{game_id}")])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        if game.message_id:
            try:
                await bot.edit_message_text(text, chat_id=game.chat_id, message_id=game.message_id,
                                            parse_mode="Markdown", reply_markup=reply_markup)
            except Exception:
                msg = await bot.send_message(game.chat_id, text, parse_mode="Markdown",
                                             reply_markup=reply_markup, message_thread_id=game.thread_id)
                game.message_id = msg.message_id
                session.commit()
        else:
            msg = await bot.send_message(game.chat_id, text, parse_mode="Markdown",
                                         reply_markup=reply_markup, message_thread_id=game.thread_id)
            game.message_id = msg.message_id
            session.commit()

# ---------- Обработка хода ----------
@router.callback_query(F.data.startswith("ttt_move:"))
async def make_move(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    _, game_id_str, cell_idx_str = callback.data.split(":")
    game_id = int(game_id_str)
    cell_idx = int(cell_idx_str)
    user_id = callback.from_user.id

    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game or game.status != 'active':
            await callback.answer("Игра уже завершена или не существует.", show_alert=True)
            return
        if game.winner_id is not None:
            await callback.answer("Игра уже закончена.", show_alert=True)
            return
        if game.turn_id != user_id:
            await callback.answer("Сейчас не ваш ход!", show_alert=True)
            return
        board = list(game.board)
        if board[cell_idx] != ' ':
            await callback.answer("Эта клетка уже занята.", show_alert=True)
            return
        symbol = 'X' if user_id == game.player_x_id else 'O'
        board[cell_idx] = symbol
        new_board = ''.join(board)
        save_move(game_id, user_id, cell_idx, symbol)
        game.last_move_at = datetime.now()
        session.commit()

        winner = check_winner(new_board)
        if winner:
            finish_game(game_id, winner=user_id)
            await finish_game_ui(bot, game_id, winner=user_id)
            return
        if all(c != ' ' for c in new_board):
            finish_game(game_id, winner=None)
            await finish_game_ui(bot, game_id, winner=None)
            return
        other_id = game.player_x_id if user_id == game.player_o_id else game.player_o_id
        game.turn_id = other_id
        game.board = new_board
        session.commit()
        await send_game_board(bot, game_id)

def check_winner(board_str):
    board = list(board_str)
    win_patterns = [
        [0,1,2],[3,4,5],[6,7,8],
        [0,3,6],[1,4,7],[2,5,8],
        [0,4,8],[2,4,6]
    ]
    for p in win_patterns:
        if board[p[0]] != ' ' and board[p[0]] == board[p[1]] == board[p[2]]:
            return board[p[0]]
    return None

# ---------- Завершение игры (UI) ----------
async def finish_game_ui(bot: Bot, game_id: int, winner: Optional[int]):
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game:
            return
        if winner:
            user = session.query(User).filter(User.telegram_id == winner).first()
            winner_name = user.name if user else str(winner)
            result_text = f"🏆 Победитель: {winner_name}! Поздравляем! 🎉"
        else:
            result_text = "🤝 Ничья!"
        try:
            await bot.edit_message_text(result_text, chat_id=game.chat_id, message_id=game.message_id, parse_mode="Markdown")
        except Exception:
            pass
        try:
            await bot.close_forum_topic(game.chat_id, game.thread_id)
        except Exception as e:
            logger.error(f"Не удалось закрыть тему: {e}")

# ---------- Сдаться через кнопку ----------
@router.callback_query(F.data.startswith("ttt_surrender:"))
async def surrender(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    game_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game or game.status != 'active':
            await callback.answer("Игра не найдена или уже завершена.", show_alert=True)
            return
        if user_id not in (game.player_x_id, game.player_o_id):
            await callback.answer("Вы не участвуете в этой игре.", show_alert=True)
            return
        winner = game.player_x_id if user_id == game.player_o_id else game.player_o_id
        finish_game(game_id, winner=winner)
        await finish_game_ui(bot, game_id, winner=winner)

# ---------- Принудительное завершение (кнопка) ----------
@router.callback_query(F.data.startswith("ttt_end:"))
async def end_game(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    game_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game:
            await callback.answer("Игра не найдена.", show_alert=True)
            return
        if user_id not in (game.player_x_id, game.player_o_id) and user_id not in ADMIN_IDS:
            await callback.answer("Только участники или админ могут завершить игру.", show_alert=True)
            return
        finish_game(game_id, winner=None)
        # Принудительно обновляем сессию, чтобы убедиться
        with get_session() as session2:
           game2 = session2.query(Game).filter(Game.id == game_id).first()
           logger.info(f"Game status after finish: {game2.status}")

        await finish_game_ui(bot, game_id, winner=None)

@router.callback_query(F.data == "ttt_noop")
async def noop(callback: CallbackQuery):
    await callback.answer("Это занятая клетка или служебная кнопка.")

# ---------- Статистика ----------
@router.message(Command("stats"))
async def stats_cmd(message: Message):
    user_id = message.from_user.id
    stats = get_player_stats(user_id)
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        name = user.name if user else "Вы"
    text = (
        f"📊 *Статистика игрока {name}*\n"
        f"🎮 Сыграно игр: {stats['games_played']}\n"
        f"🏆 Побед: {stats['games_won']}\n"
        f"🤝 Ничьих: {stats['games_drawn']}"
    )
    await message.answer(text, parse_mode="Markdown")

# ---------- Статус активной игры ----------
@router.message(Command("ttt_status"))
async def ttt_status(message: Message):
    user_id = message.from_user.id
    game = get_active_game(user_id)
    if not game:
        await message.answer("У вас нет активных игр.")
        return
    with get_session() as session:
        opponent_id = game.player_x_id if game.player_o_id == user_id else game.player_o_id
        opponent = session.query(User).filter(User.telegram_id == opponent_id).first()
        opponent_name = opponent.name if opponent else str(opponent_id)
        free = game.board.count(' ')
        text = (
            f"🎮 У вас есть активная игра против {opponent_name}.\n"
            f"Свободных клеток: {free}\n"
            f"Ваш ход: {'да' if game.turn_id == user_id else 'нет'}\n"
            f"Игра начата: {game.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"Последний ход: {game.last_move_at.strftime('%d.%m.%Y %H:%M') if game.last_move_at else 'неизвестно'}\n\n"
            f"Чтобы продолжить, откройте игровую тему в группе и сделайте ход."
        )
        await message.answer(text)

# ---------- Принудительный выход из зависшей игры (через команду) ----------
@router.message(Command("ttt_abandon"))
async def abandon_game(message: Message):
    user_id = message.from_user.id
    game = get_active_game(user_id)
    if not game:
        await message.answer("❌ У вас нет активной игры.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, завершить игру", callback_data=f"ttt_abandon_confirm:{game.id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ttt_abandon_cancel")]
    ])
    await message.answer("⚠️ Вы действительно хотите завершить текущую игру? Игра будет считаться ничьей.", reply_markup=kb)

@router.callback_query(F.data.startswith("ttt_abandon_confirm:"))
async def abandon_confirm(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    game_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game or game.status != 'active':
            await callback.message.edit_text("❌ Игра уже завершена.")
            return
        if user_id not in (game.player_x_id, game.player_o_id):
            await callback.message.edit_text("❌ Вы не участник этой игры.")
            return
        finish_game(game_id, winner=None)
        await callback.message.edit_text("✅ Игра завершена (ничья). Теперь вы можете начать новую.")
        try:
            await bot.close_forum_topic(game.chat_id, game.thread_id)
        except Exception as e:
            logger.error(f"Не удалось закрыть тему: {e}")
        try:
            await bot.edit_message_text("🤝 Игра завершена досрочно (ничья).", chat_id=game.chat_id, message_id=game.message_id)
        except Exception:
            pass

@router.callback_query(F.data == "ttt_abandon_cancel")
async def abandon_cancel(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("❌ Отмена. Игра продолжается.")

# ---------- Админская команда принудительного завершения ----------
@router.message(Command("ttt_force_end"))
async def force_end_game(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только для админов.")
        return
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("❌ Используйте: `/ttt_force_end <game_id>`", parse_mode="Markdown")
        return
    game_id = int(args[1])
    finish_game(game_id, winner=None)
    await message.answer(f"✅ Игра #{game_id} принудительно завершена (ничья).")
