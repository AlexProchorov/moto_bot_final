# database/crud.py
from sqlalchemy import func
from .engine import get_session
from datetime import datetime, timedelta
import logging
from sqlalchemy import and_, or_


from .models import DailyActiveTopic
from .models import User, Ride, RideParticipant, DailyActiveTopic, Setting

logger = logging.getLogger(__name__)

# ========== СУЩЕСТВУЮЩИЕ ФУНКЦИИ (если есть) ==========
# Они должны использовать get_session() аналогично новым.
# Пример: вместо async with async_session() as session: → with get_session() as session:

# ========== НОВЫЕ ФУНКЦИИ ==========
def get_all_users():
    """Возвращает всех зарегистрированных пользователей."""
    with get_session() as session:
        users = session.query(User).all()
        return [
            {
                "id": u.telegram_id,
                "name": u.name,
                "username": u.username,
                "bike": f"{u.bike_brand} {u.bike_model}",
                "birthday": u.birthday,
            }
            for u in users
        ]

def get_all_birthdays_sorted():
    with get_session() as session:
        users = session.query(User).filter(User.birthday.isnot(None)).all()
        birthdays = []
        for u in users:
            try:
                day, month = map(int, u.birthday.split('.'))
                birthdays.append({
                    "name": u.name,
                    "username": u.username,
                    "birthday": u.birthday,
                    "sort_key": (month, day)
                })
            except:
                continue
        birthdays.sort(key=lambda x: x["sort_key"])
        return birthdays

def get_upcoming_birthdays(days=30):
    today = datetime.now()
    upcoming = []
    with get_session() as session:
        users = session.query(User).filter(User.birthday.isnot(None)).all()
        for u in users:
            try:
                day, month = map(int, u.birthday.split('.'))
                birthday_this_year = datetime(today.year, month, day)
                if birthday_this_year < today:
                    birthday_this_year = datetime(today.year + 1, month, day)
                delta = (birthday_this_year - today).days
                if 0 <= delta <= days:
                    upcoming.append({
                        "name": u.name,
                        "username": u.username,
                        "birthday": u.birthday,
                        "days_left": delta,
                        "date": birthday_this_year
                    })
            except:
                continue
        upcoming.sort(key=lambda x: x["date"])
        return upcoming

def delete_user_by_id(telegram_id: int) -> bool:
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            session.delete(user)
            return True
        return False

def user_exists(telegram_id: int) -> bool:
    with get_session() as session:
        return session.query(User).filter(User.telegram_id == telegram_id).first() is not None

def get_today_birthdays():
    """Возвращает список именинников сегодня с полями id, name, username."""
    today_str = datetime.now().strftime("%d.%m")
    with get_session() as session:
        users = session.query(User).filter(User.birthday == today_str).all()
        result = []
        for u in users:
            result.append({
                "id": u.telegram_id,
                "name": u.name if u.name else "Неизвестный",
                "username": u.username
            })
        return result



def set_user_active(telegram_id: int, hours: int = 12, topic_id: int = None) -> None:
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.active_until = datetime.now() + timedelta(hours=hours)
            user.active_topic_id = topic_id
            session.commit()

def clear_user_active(telegram_id: int) -> None:
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.active_until = None
            user.active_topic_id = None
            session.commit()

def get_active_users():
    """Возвращает список пользователей, у которых active_until > now."""
    with get_session() as session:
        users = session.query(User).filter(User.active_until > datetime.now()).all()
        return [{"id": u.telegram_id, "name": u.name, "username": u.username} for u in users]

def get_user_active_topic_id(telegram_id: int):
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        return user.active_topic_id if user else None

# === Запланированные заезды ===
def create_ride(title: str, date: datetime, location: str, description: str, created_by: int, thread_id: int = None) -> int:
    with get_session() as session:
        ride = Ride(
            title=title,
            date=date,
            location=location,
            description=description,
            created_by=created_by,
            message_thread_id=thread_id
        )
        session.add(ride)
        session.commit()
        return ride.id

def get_active_rides():
    """Список активных заездов (is_active=True) с датой в будущем, возвращает список словарей."""
    with get_session() as session:
        rides = session.query(Ride).filter(
            Ride.is_active == True,
            Ride.date > datetime.now()
        ).order_by(Ride.date).all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "date": r.date,
                "location": r.location,
                "description": r.description,
                "message_thread_id": r.message_thread_id,
                "created_by": r.created_by
            }
            for r in rides
        ]

def get_ride_by_id(ride_id: int):
    """Возвращает словарь с данными заезда или None."""
    with get_session() as session:
        ride = session.query(Ride).filter(Ride.id == ride_id).first()
        if ride:
            return {
                "id": ride.id,
                "title": ride.title,
                "date": ride.date,
                "location": ride.location,
                "description": ride.description,
                "message_thread_id": ride.message_thread_id,
                "is_active": ride.is_active,
                "created_by": ride.created_by
            }
        return None

def end_ride(ride_id: int):
    """Завершить заезд (архивировать)."""
    with get_session() as session:
        ride = session.query(Ride).filter(Ride.id == ride_id).first()
        if ride:
            ride.is_active = False
            session.commit()

def add_participant(ride_id: int, user_id: int):
    with get_session() as session:
        # Проверяем, не участвует ли уже
        exists = session.query(RideParticipant).filter(
            RideParticipant.ride_id == ride_id,
            RideParticipant.user_id == user_id
        ).first()
        if not exists:
            session.add(RideParticipant(ride_id=ride_id, user_id=user_id))
            session.commit()
            return True
        return False

def remove_participant(ride_id: int, user_id: int):
    with get_session() as session:
        session.query(RideParticipant).filter(
            RideParticipant.ride_id == ride_id,
            RideParticipant.user_id == user_id
        ).delete()
        session.commit()

def get_participants_count(ride_id: int) -> int:
    with get_session() as session:
        return session.query(RideParticipant).filter(RideParticipant.ride_id == ride_id).count()

def get_user_rides(user_id: int):
    """Возвращает список активных заездов, в которых участвует пользователь."""
    with get_session() as session:
        rides = session.query(Ride).join(RideParticipant).filter(
            RideParticipant.user_id == user_id,
            Ride.is_active == True,
            Ride.date > datetime.now()
        ).all()
        return rides



def get_today_active_topic():
    today_str = datetime.now().strftime("%d.%m")
    with get_session() as session:
        topic = session.query(DailyActiveTopic).filter(
            DailyActiveTopic.date == today_str,
            DailyActiveTopic.expires_at > datetime.now()
        ).first()
        return topic.message_thread_id if topic else None

def create_today_active_topic(thread_id: int):
    today_str = datetime.now().strftime("%d.%m")
    expires = datetime.now() + timedelta(hours=12)
    with get_session() as session:
        session.query(DailyActiveTopic).filter(DailyActiveTopic.date == today_str).delete()
        topic = DailyActiveTopic(
            date=today_str,
            message_thread_id=thread_id,
            expires_at=expires
        )
        session.add(topic)
        session.commit()

def clear_expired_daily_topics():
    """Удаляет истекшие темы из БД (вызывается фоном)."""
    with get_session() as session:
        session.query(DailyActiveTopic).filter(DailyActiveTopic.expires_at <= datetime.now()).delete()
        session.commit()

def get_setting(key: str, default: str = 'false') -> str:
    with get_session() as session:
        setting = session.query(Setting).filter(Setting.key == key).first()
        if setting:
            return setting.value
        return default

def set_setting(key: str, value: str):
    with get_session() as session:
        setting = session.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value = value
        else:
            session.add(Setting(key=key, value=value))
        session.commit()

def clear_today_active_topic():
    today_str = datetime.now().strftime("%d.%m")
    with get_session() as session:
        session.query(DailyActiveTopic).filter(DailyActiveTopic.date == today_str).delete()
        session.commit()

def get_users_with_district():
    with get_session() as session:
        users = session.query(User).filter(User.district.isnot(None)).all()
        return [{"id": u.telegram_id, "name": u.name, "district": u.district} for u in users]

def get_users_by_district(district: str):
    """Возвращает список пользователей с указанным округом (id, name, username)."""
    with get_session() as session:
        users = session.query(User).filter(User.district == district).all()
        return [{"id": u.telegram_id, "name": u.name, "username": u.username} for u in users]


# ========== Игровые функции ==========
from sqlalchemy import and_, or_
from .models import Game, GameMove, PlayerStats

def get_active_game(player_id: int):
    """Возвращает активную игру, в которой участвует игрок."""
    with get_session() as session:
        return session.query(Game).filter(
            and_(
                Game.status == 'active',
                or_(Game.player_x_id == player_id, Game.player_o_id == player_id)
            )
        ).first()

def create_game(chat_id: int, thread_id: int, player_x_id: int, player_o_id: int, first_player_id: int):
    """Создаёт новую игру и возвращает объект Game."""
    with get_session() as session:
        game = Game(
            chat_id=chat_id,
            thread_id=thread_id,
            player_x_id=player_x_id,
            player_o_id=player_o_id,
            turn_id=first_player_id,
            board=' ' * 9,
            status='active'
        )
        session.add(game)
        session.commit()
        return game

def save_move(game_id: int, player_id: int, position: int, symbol: str):
    with get_session() as session:
        move = GameMove(game_id=game_id, player_id=player_id, position=position, symbol=symbol)
        session.add(move)
        session.commit()


def _update_stats(player_x_id: int, player_o_id: int, winner_id: int = None):
    with get_session() as session:
        for pid in (player_x_id, player_o_id):
            stats = session.query(PlayerStats).filter(PlayerStats.telegram_id == pid).first()
            if not stats:
                stats = PlayerStats(telegram_id=pid, games_played=0, games_won=0, games_drawn=0)
                session.add(stats)
            stats.games_played += 1
            if winner_id is None:
                stats.games_drawn += 1
            elif pid == winner_id:
                stats.games_won += 1
            session.commit()

def finish_game(game_id: int, winner_id=None):
    """Завершает игру, обновляет статус и статистику."""
    from datetime import datetime
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game:
            return
        if game.status == 'finished':
            return
        game.status = 'finished'
        game.finished_at = datetime.now()
        if winner_id:
            game.winner_id = winner_id
        session.commit()
        # Обновляем статистику
        _update_stats(game.player_x_id, game.player_o_id, winner_id)
        return game

def _update_stats(player_x_id: int, player_o_id: int, winner_id: int = None):
    with get_session() as session:
        for pid in (player_x_id, player_o_id):
            stats = session.query(PlayerStats).filter(PlayerStats.telegram_id == pid).first()
            if not stats:
                stats = PlayerStats(telegram_id=pid, games_played=0, games_won=0, games_drawn=0)
                session.add(stats)
            stats.games_played += 1
            if winner_id is None:
                stats.games_drawn += 1
            elif pid == winner_id:
                stats.games_won += 1
            session.commit()


def get_player_stats(telegram_id: int):
    with get_session() as session:
        stats = session.query(PlayerStats).filter(PlayerStats.telegram_id == telegram_id).first()
        if not stats:
            return {"games_played": 0, "games_won": 0, "games_drawn": 0}
        return {"games_played": stats.games_played, "games_won": stats.games_won, "games_drawn": stats.games_drawn}


def get_stale_game_for_player(player_id: int, timeout_hours=168):  # 7 дней
    """Возвращает активную игру игрока, если последний ход был более timeout_hours назад."""
    from datetime import datetime, timedelta
    with get_session() as session:
        threshold = datetime.now() - timedelta(hours=timeout_hours)
        return session.query(Game).filter(
            Game.status == 'active',
            or_(Game.player_x_id == player_id, Game.player_o_id == player_id),
            Game.last_move_at <= threshold
        ).first()

def auto_abandon_stale_game(player_id: int):
    """Завершает зависшую игру игрока ничьёй и возвращает True, если была завершена."""
    game = get_stale_game_for_player(player_id)
    if game:
        finish_game(game.id, winner=None)
        return True
    return False


def get_stale_game_for_player(player_id: int, timeout_hours=168):  # 7 дней
    from datetime import datetime, timedelta
    with get_session() as session:
        threshold = datetime.now() - timedelta(hours=timeout_hours)
        return session.query(Game).filter(
            Game.status == 'active',
            or_(Game.player_x_id == player_id, Game.player_o_id == player_id),
            Game.last_move_at <= threshold
        ).first()

def auto_abandon_stale_game(player_id: int):
    """Завершает зависшую игру игрока ничьёй и возвращает True, если была завершена."""
    game = get_stale_game_for_player(player_id)
    if game:
        finish_game(game.id, winner=None)
        return True
    return False
