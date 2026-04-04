import re
from datetime import datetime

def validate_name(name: str) -> bool:
    if not name or len(name) < 2 or len(name) > 100:
        return False
    if not re.match(r'^[a-zA-Zа-яА-ЯёЁ\s\-]+$', name):
        return False
    return True

def validate_birthday(birthday_str: str) -> str | None:
    birthday_str = birthday_str.strip().replace('-', '.')
    try:
        parts = birthday_str.split('.')
        if len(parts) != 2:
            return None
        day = int(parts[0])
        month = int(parts[1])
    except ValueError:
        return None
    if not (1 <= month <= 12):
        return None
    # Проверка корректности дня для месяца (используем 2000 високосный)
    try:
        datetime(2000, month, day)
    except ValueError:
        return None
    return f"{month:02d}-{day:02d}"

def validate_year(year_str: str) -> int | None:
    try:
        year = int(year_str)
    except ValueError:
        return None
    current_year = datetime.now().year
    if year < 1900 or year > current_year + 1:
        return None
    return year
