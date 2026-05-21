# database/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, BigInteger, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import enum
from sqlalchemy.orm import relationship
from sqlalchemy import Date
from sqlalchemy.types import JSON 

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    name = Column(String(255), nullable=False)
    birthday = Column(String(10), nullable=True)  # формат ДД.ММ
    bike_brand = Column(String(100), nullable=True)
    bike_model = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    rules_accepted = Column(Boolean, default=False)
    active_until = Column(DateTime, nullable=True)
    active_topic_id = Column(Integer, nullable=True)
    registered_at = Column(DateTime, server_default=func.now())
    weather_notifications = Column(Boolean, default=False)

class Ride(Base):
    __tablename__ = 'rides'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    date = Column(DateTime, nullable=False)
    location = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(BigInteger, nullable=False)
    message_thread_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)

class RideParticipant(Base):
    __tablename__ = 'ride_participants'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ride_id = Column(Integer, ForeignKey('rides.id'), nullable=False)
    user_id = Column(BigInteger, nullable=False)

class DailyActiveTopic(Base):
    __tablename__ = 'daily_active_topics'
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False)  # ДД.ММ
    message_thread_id = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)

class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)

class Game(Base):
    __tablename__ = 'games'
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False)
    thread_id = Column(Integer, nullable=False)
    player_x_id = Column(BigInteger, nullable=False)
    player_o_id = Column(BigInteger, nullable=False)
    turn_id = Column(BigInteger, nullable=True)
    board = Column(String(9), default=' ' * 9)
    status = Column(String(20), default='active')  # active, waiting_deletion, finished
    winner_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    last_move_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    message_id = Column(Integer, nullable=True)           # ID сообщения с игровым полем в группе
    player_x_message_id = Column(Integer, nullable=True)  # ID сообщения в ЛС игрока X
    player_o_message_id = Column(Integer, nullable=True)  # ID сообщения в ЛС игрока O

class GameMove(Base):
    __tablename__ = 'game_moves'
    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey('games.id'), nullable=False)
    player_id = Column(BigInteger, nullable=False)
    position = Column(Integer, nullable=False)
    symbol = Column(String(1), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class PlayerStats(Base):
    __tablename__ = 'player_stats'
    telegram_id = Column(BigInteger, primary_key=True)
    games_played = Column(Integer, default=0)
    games_won = Column(Integer, default=0)
    games_drawn = Column(Integer, default=0)



# ---------- Модели для сервиса мойки (новая версия) ----------
class WashService(Base):
    __tablename__ = "wash_service"
    id = Column(Integer, primary_key=True)
    is_active = Column(Boolean, default=True)          # работает ли мойка
    address = Column(String(255), nullable=True)       # адрес мойки
    description = Column(Text, nullable=True)          # описание
    photos = Column(JSON, default=list)                # список file_id фотографий

class WashSubtype(Base):
    __tablename__ = "wash_subtypes"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)         # "С цепью", "Без цепи"
    price = Column(Integer, nullable=False)            # цена в рублях

class WorkSchedule(Base):
    __tablename__ = "work_schedule"
    id = Column(Integer, primary_key=True)
    day_of_week = Column(Integer, nullable=False)      # 0-6 (пн=0)
    is_working = Column(Boolean, default=True)         # рабочий день или выходной
    hours = Column(JSON, default=list)                 # список часов, например [10,11,12,13,14,15,16,17,18]

class WashWorker(Base):
    __tablename__ = "wash_workers"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)   # telegram_id
    name = Column(String(100), nullable=False)