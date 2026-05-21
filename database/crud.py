# database/crud.py
from sqlalchemy import func
from .engine import get_session
from datetime import datetime, timedelta
import logging
from sqlalchemy import and_, or_
import asyncio

from .models import DailyActiveTopic
from .models import User, Ride, RideParticipant, DailyActiveTopic, Setting
from .models import Game, GameMove, PlayerStats

logger = logging.getLogger(__name__)

# ========== СУЩЕСТВУЮЩИЕ ФУНКЦИИ ==========
def get_all_users():
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
    with get_session() as session:
        ride = session.query(Ride).filter(Ride.id == ride_id).first()
        if ride:
            ride.is_active = False
            session.commit()

def add_participant(ride_id: int, user_id: int):
    with get_session() as session:
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
    with get_session() as session:
        users = session.query(User).filter(User.district == district).all()
        return [{"id": u.telegram_id, "name": u.name, "username": u.username} for u in users]

def get_registered_users_count():
    with get_session() as session:
        return session.query(User).count()

# ========== Игровые функции ==========
def get_active_game(player_id: int):
    with get_session() as session:
        return session.query(Game).filter(
            and_(
                Game.status == 'active',
                or_(Game.player_x_id == player_id, Game.player_o_id == player_id)
            )
        ).first()

def create_game(chat_id: int, thread_id: int, player_x_id: int, player_o_id: int, first_player_id: int) -> int:
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
        return game.id

def is_any_game_active_or_pending():
    with get_session() as session:
        count = session.query(Game).filter(Game.status.in_(['active', 'waiting_deletion'])).count()
        return count > 0

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

def finish_game(game_id: int, winner: int = None, bot=None, chat_id=None, thread_id=None):
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game or game.status not in ('active', 'waiting_deletion'):
            return
        if winner:
            game.winner_id = winner
        game.status = 'waiting_deletion'
        game.finished_at = datetime.now()
        session.commit()
        _update_stats(game.player_x_id, game.player_o_id, winner)
        if bot and chat_id and thread_id:
            schedule_game_cleanup(game_id, chat_id, thread_id, bot)
        else:
            finalize_game(game_id)

def get_player_stats(telegram_id: int):
    with get_session() as session:
        stats = session.query(PlayerStats).filter(PlayerStats.telegram_id == telegram_id).first()
        if not stats:
            return {"games_played": 0, "games_won": 0, "games_drawn": 0}
        return {"games_played": stats.games_played, "games_won": stats.games_won, "games_drawn": stats.games_drawn}

def get_stale_game_for_player(player_id: int, timeout_hours=168):
    with get_session() as session:
        threshold = datetime.now() - timedelta(hours=timeout_hours)
        return session.query(Game).filter(
            Game.status == 'active',
            or_(Game.player_x_id == player_id, Game.player_o_id == player_id),
            Game.last_move_at <= threshold
        ).first()

def auto_abandon_stale_game(player_id: int):
    game = get_stale_game_for_player(player_id)
    if game:
        finish_game(game.id, winner=None)
        return True
    return False

def update_user_rules_accepted(telegram_id: int, accepted: bool):
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.rules_accepted = accepted
            session.commit()

def get_user_by_telegram_id(telegram_id: int):
    with get_session() as session:
        return session.query(User).filter(User.telegram_id == telegram_id).first()

def get_user_bike_details(telegram_id: int):
    with get_session() as session:
        user_row = session.query(User.bike_brand, User.bike_model).filter(User.telegram_id == telegram_id).first()
        if user_row:
            return user_row.bike_brand, user_row.bike_model
        return None, None

def get_stale_game_by_timeout(timeout_minutes=5):
    with get_session() as session:
        threshold = datetime.now() - timedelta(minutes=timeout_minutes)
        return session.query(Game).filter(
            Game.status == 'active',
            Game.last_move_at <= threshold
        ).first()

def finish_game_timeout(game_id: int):
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if not game or game.status != 'active':
            return
        if game.turn_id is None or game.last_move_at is None:
            finish_game(game_id, winner=None)
        else:
            finish_game(game_id, winner=game.turn_id)

def reset_all_active_games():
    with get_session() as session:
        session.query(Game).filter(Game.status.in_(['active', 'waiting_deletion'])).update(
            {'status': 'finished', 'finished_at': datetime.now()}
        )
        session.commit()

def schedule_game_cleanup(game_id: int, chat_id: int, thread_id: int, bot):
    async def delete_later():
        await asyncio.sleep(60)
        try:
            await bot.delete_forum_topic(chat_id, thread_id)
            logger.info(f"Deleted forum topic {thread_id} for game {game_id}")
        except Exception as e:
            logger.error(f"Failed to delete topic {thread_id}: {e}")
        finalize_game(game_id)
    asyncio.create_task(delete_later())

def finalize_game(game_id: int):
    with get_session() as session:
        game = session.query(Game).filter(Game.id == game_id).first()
        if game and game.status == 'waiting_deletion':
            game.status = 'finished'
            session.commit()

def get_users_with_notifications_enabled():
    with get_session() as session:
        users = session.query(User).filter(User.district.isnot(None), User.weather_notifications == True).all()
        return [{"id": u.telegram_id, "name": u.name, "district": u.district} for u in users]

def update_user_weather_notifications(telegram_id: int, enabled: bool):
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.weather_notifications = enabled
            session.commit()