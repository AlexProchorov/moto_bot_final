import logging
from sqlalchemy.orm import Session
from database.engine import get_session
from database.models import WashService, WashSubtype, WorkSchedule, WashWorker
import json

logger = logging.getLogger(__name__)

# ---------- WashService ----------
def get_or_create_service():
    with get_session() as session:
        service = session.query(WashService).first()
        if not service:
            service = WashService(is_active=True, address="", description="", photos=[])
            session.add(service)
            session.commit()
        return service

def update_service(**kwargs):
    with get_session() as session:
        service = session.query(WashService).first()
        if service:
            for key, value in kwargs.items():
                setattr(service, key, value)
            session.commit()

# ---------- WashSubtype ----------
def get_subtypes():
    with get_session() as session:
        return session.query(WashSubtype).all()

def update_subtype_price(subtype_id: int, new_price: int):
    with get_session() as session:
        subtype = session.query(WashSubtype).filter(WashSubtype.id == subtype_id).first()
        if subtype:
            subtype.price = new_price
            session.commit()

def init_default_subtypes():
    """Создаёт подтипы, если их нет."""
    with get_session() as session:
        if session.query(WashSubtype).count() == 0:
            session.add(WashSubtype(name="С цепью", price=500))
            session.add(WashSubtype(name="Без цепи", price=400))
            session.commit()

# ---------- WorkSchedule ----------
def get_schedule(day_of_week: int):
    with get_session() as session:
        return session.query(WorkSchedule).filter(WorkSchedule.day_of_week == day_of_week).first()

def get_all_schedules():
    with get_session() as session:
        schedules = {d.day_of_week: d for d in session.query(WorkSchedule).all()}
        # Заполняем отсутствующие дни значениями по умолчанию (рабочий день с 10 до 19)
        for dow in range(7):
            if dow not in schedules:
                schedules[dow] = WorkSchedule(day_of_week=dow, is_working=True, hours=[10,11,12,13,14,15,16,17,18,19])
        return [schedules[dow] for dow in range(7)]

def update_schedule(day_of_week: int, is_working: bool = None, hours: list = None):
    with get_session() as session:
        sched = session.query(WorkSchedule).filter(WorkSchedule.day_of_week == day_of_week).first()
        if not sched:
            sched = WorkSchedule(day_of_week=day_of_week, is_working=True, hours=hours or [10,11,12,13,14,15,16,17,18,19])
            session.add(sched)
        if is_working is not None:
            sched.is_working = is_working
        if hours is not None:
            sched.hours = hours
        session.commit()

# ---------- WashWorker ----------
def get_all_workers():
    with get_session() as session:
        return session.query(WashWorker).all()

def add_worker(telegram_id: int, name: str):
    with get_session() as session:
        worker = WashWorker(user_id=telegram_id, name=name)
        session.add(worker)
        session.commit()

def delete_worker(telegram_id: int):
    with get_session() as session:
        worker = session.query(WashWorker).filter(WashWorker.user_id == telegram_id).first()
        if worker:
            session.delete(worker)
            session.commit()

def is_worker(telegram_id: int) -> bool:
    with get_session() as session:
        return session.query(WashWorker).filter(WashWorker.user_id == telegram_id).first() is not None