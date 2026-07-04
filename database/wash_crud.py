import json
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from database.engine import get_session
from database.models import WashService, WashSubtype, WorkSchedule, WashWorker, TimeSlot, Booking

# ---------- Общие ----------
def get_or_create_wash_service():
    with get_session() as session:
        service = session.query(WashService).first()
        if not service:
            service = WashService()
            session.add(service)
            session.commit()
        return service

def update_service(**kwargs):
    with get_session() as session:
        service = session.query(WashService).first()
        if service:
            for k, v in kwargs.items():
                setattr(service, k, v)
            session.commit()

def get_subtypes():
    with get_session() as session:
        return session.query(WashSubtype).all()

def get_subtype_by_id(subtype_id: int):
    with get_session() as session:
        return session.query(WashSubtype).filter(WashSubtype.id == subtype_id).first()

def update_subtype_price(subtype_id: int, new_price: int):
    with get_session() as session:
        subtype = session.query(WashSubtype).filter(WashSubtype.id == subtype_id).first()
        if subtype:
            subtype.price = new_price
            session.commit()

def init_default_subtypes():
    with get_session() as session:
        if session.query(WashSubtype).count() == 0:
            session.add(WashSubtype(name="3-х фазная мойка", price=500))
            session.add(WashSubtype(name="3-х фазная мойка, чистка, мойка и смазка цепи", price=800))
            session.add(WashSubtype(name="3-х фазная мойка, мойка кисточкой, чистка, мойка и смазка цепи", price=1000))
            session.commit()

# ---------- Исполнители ----------
def add_worker(telegram_id: int, name: str):
    with get_session() as session:
        service = get_or_create_wash_service()
        worker = WashWorker(user_id=telegram_id, name=name, service_id=service.id, is_working=True)
        session.add(worker)
        session.commit()
        return worker

def get_worker_by_telegram_id(telegram_id: int):
    with get_session() as session:
        return session.query(WashWorker).filter(WashWorker.user_id == telegram_id).first()

def get_all_workers():
    with get_session() as session:
        return session.query(WashWorker).all()

def is_worker(telegram_id: int) -> bool:
    return get_worker_by_telegram_id(telegram_id) is not None

def delete_worker(telegram_id: int):
    with get_session() as session:
        worker = session.query(WashWorker).filter(WashWorker.user_id == telegram_id).first()
        if worker:
            session.delete(worker)
            session.commit()

# ---------- Расписание ----------
def get_all_schedules():
    """Возвращает список расписаний из БД (только то, что есть)."""
    with get_session() as session:
        schedules = session.query(WorkSchedule).all()
        # Возвращаем список, дополняя отсутствующие дни None (или создаём пустые объекты)
        result = []
        for dow in range(7):
            found = next((s for s in schedules if s.day_of_week == dow), None)
            result.append(found)
        return result


def update_schedule(worker_id: int, day_of_week: int, is_working: bool = None, hours: list = None, is_day_off: bool = None):
    with get_session() as session:
        sched = session.query(WorkSchedule).filter(
            WorkSchedule.worker_id == worker_id,
            WorkSchedule.day_of_week == day_of_week
        ).first()
        if not sched:
            # Создаём новую запись с указанным worker_id
            sched = WorkSchedule(worker_id=worker_id, day_of_week=day_of_week, is_working=True, hours=[], is_day_off=False)
            session.add(sched)
        if is_working is not None:
            sched.is_working = is_working
        if hours is not None:
            sched.hours = hours
        if is_day_off is not None:
            sched.is_day_off = is_day_off
        session.commit()


def ensure_worker_schedule(worker_id: int):
    """Проверяет, есть ли у исполнителя расписание; если нет – создаёт."""
    with get_session() as session:
        for dow in range(7):
            exists = session.query(WorkSchedule).filter(
                WorkSchedule.worker_id == worker_id,
                WorkSchedule.day_of_week == dow
            ).first()
            if not exists:
                sched = WorkSchedule(
                    worker_id=worker_id,
                    day_of_week=dow,
                    is_working=True,
                    hours=list(range(9,21)),
                    is_day_off=False
                )
                session.add(sched)
        session.commit()

# ---------- Слоты ----------
def generate_slots_for_date(worker_id: int, target_date: date):
    dow = target_date.weekday()
    with get_session() as session:
        schedule = session.query(WorkSchedule).filter(
            WorkSchedule.worker_id == worker_id,
            WorkSchedule.day_of_week == dow
        ).first()
        if not schedule or not schedule.is_working or schedule.is_day_off:
            return []
        created = []
        for hour in schedule.hours:
            existing = session.query(TimeSlot).filter(
                TimeSlot.worker_id == worker_id,
                TimeSlot.date == target_date,
                TimeSlot.hour == hour
            ).first()
            if not existing:
                new_slot = TimeSlot(
                    worker_id=worker_id,
                    date=target_date,
                    hour=hour,
                    booked_bikes=0,
                    is_available=True
                )
                session.add(new_slot)
                created.append(new_slot)
            else:
                created.append(existing)
        session.commit()
        return created

def generate_slots_for_range(worker_id: int, start_date: date, days: int = 7):
    for i in range(days):
        generate_slots_for_date(worker_id, start_date + timedelta(days=i))

def get_available_slots(worker_id: int, target_date: date):
    with get_session() as session:
        service = get_or_create_wash_service()
        max_bikes = service.max_bikes_per_slot
        slots = session.query(TimeSlot).filter(
            TimeSlot.worker_id == worker_id,
            TimeSlot.date == target_date,
            TimeSlot.booked_bikes < max_bikes
        ).order_by(TimeSlot.hour).all()
        return slots

# ---------- Бронирование ----------
def create_booking_with_status(user_id: int, slot_id: int, subtype_id: int, bikes_count: int = 1, status: str = "pending"):
    with get_session() as session:
        slot = session.query(TimeSlot).filter(TimeSlot.id == slot_id).first()
        if not slot:
            return None
        service = get_or_create_wash_service()
        if slot.booked_bikes + bikes_count > service.max_bikes_per_slot:
            return None
        booking = Booking(
            user_id=user_id,
            slot_id=slot_id,
            service_id=service.id,
            subtype_id=subtype_id,
            bikes_count=bikes_count,
            status=status,
            created_at=datetime.now()
        )
        slot.booked_bikes += bikes_count
        if slot.booked_bikes >= service.max_bikes_per_slot:
            slot.is_available = False
        session.add(booking)
        session.commit()
        return booking

def confirm_booking(booking_id: int):
    with get_session() as session:
        booking = session.query(Booking).filter(Booking.id == booking_id).first()
        if booking and booking.status == "pending":
            booking.status = "confirmed"
            session.commit()
            return True
        return False


def reject_booking(booking_id: int):
    with get_session() as session:
        booking = session.query(Booking).filter(Booking.id == booking_id).first()
        if booking and booking.status == "pending":
            slot = session.query(TimeSlot).filter(TimeSlot.id == booking.slot_id).first()
            if slot:
                slot.booked_bikes -= booking.bikes_count
                if slot.booked_bikes < get_or_create_wash_service().max_bikes_per_slot:
                    slot.is_available = True
            session.delete(booking)
            session.commit()
            return True
        return False


def regenerate_slots_for_worker(worker_id: int, days_ahead: int = 7):
    """Удаляет все старые слоты на ближайшие days_ahead дней и создаёт новые по текущему расписанию (в одной транзакции)."""
    from datetime import date, timedelta
    from database.models import TimeSlot
    start_date = date.today()
    with get_session() as session:
        # Удаляем слоты
        for i in range(days_ahead):
            target_date = start_date + timedelta(days=i)
            session.query(TimeSlot).filter(
                TimeSlot.worker_id == worker_id,
                TimeSlot.date == target_date
            ).delete()
        session.commit()
        # Создаём новые
        for i in range(days_ahead):
            target_date = start_date + timedelta(days=i)
            _generate_slots_for_date_with_session(session, worker_id, target_date)
        session.commit()

def _generate_slots_for_date_with_session(session, worker_id: int, target_date: date):
    """Вспомогательная функция для генерации слотов в переданной сессии (без отдельного commit)."""
    dow = target_date.weekday()
    schedule = session.query(WorkSchedule).filter(
        WorkSchedule.worker_id == worker_id,
        WorkSchedule.day_of_week == dow
    ).first()
    if not schedule or not schedule.is_working or schedule.is_day_off:
        return
    for hour in schedule.hours:
        existing = session.query(TimeSlot).filter(
            TimeSlot.worker_id == worker_id,
            TimeSlot.date == target_date,
            TimeSlot.hour == hour
        ).first()
        if not existing:
            new_slot = TimeSlot(
                worker_id=worker_id,
                date=target_date,
                hour=hour,
                booked_bikes=0,
                is_available=True
            )
            session.add(new_slot)


def ensure_worker_schedule_exists(worker_id: int):
    """Создаёт записи в work_schedule для всех дней, если их нет (по умолчанию – выходные)."""
    with get_session() as session:
        for dow in range(7):
            exists = session.query(WorkSchedule).filter(
                WorkSchedule.worker_id == worker_id,
                WorkSchedule.day_of_week == dow
            ).first()
            if not exists:
                sched = WorkSchedule(worker_id=worker_id, day_of_week=dow, is_working=False, hours=[], is_day_off=True)
                session.add(sched)
        session.commit()
