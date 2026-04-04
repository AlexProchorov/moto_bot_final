from datetime import datetime

def days_until_birthday(birthday: str) -> int:
    today = datetime.now().date()
    month, day = map(int, birthday.split('-'))
    birthday_this_year = datetime(today.year, month, day).date()
    if birthday_this_year < today:
        birthday_this_year = datetime(today.year + 1, month, day).date()
    delta = birthday_this_year - today
    return delta.days

def get_user_link(telegram_id: int, username: str | None) -> str:
    if username:
        return f"@{username}"
    else:
        return f"[ссылка](tg://user?id={telegram_id})"
