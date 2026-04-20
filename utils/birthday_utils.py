from datetime import datetime
from typing import Optional


def days_until_birthday(birthday: str) -> int:
    today = datetime.now().date()
    month, day = map(int, birthday.split('-'))
    birthday_this_year = datetime(today.year, month, day).date()
    if birthday_this_year < today:
        birthday_this_year = datetime(today.year + 1, month, day).date()
    return (birthday_this_year - today).days


def get_user_link(telegram_id: int, username: str | None) -> str:
    if username:
        return f"@{username}"
    else:
        return f"[ссылка](tg://user?id={telegram_id})"


def get_user_mention(telegram_id: int, username: Optional[str], name: str) -> str:
    """Возвращает строку вида 'Имя (@username)' или просто 'Имя'."""
    # Защита от пустого имени
    if not name or not name.strip():
        name = f"Участник {telegram_id}"
    if username:
        return f"{name} (@{username})"
    else:
        return name