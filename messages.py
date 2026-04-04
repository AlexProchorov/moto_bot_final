def greeting_announcement() -> str:
    return "Друзья! Начинаем регистрацию участников. Нажмите кнопку ниже, чтобы заполнить анкету."

def registration_start() -> str:
    return "Давайте зарегистрируем вас в мотосообществе! Пожалуйста, введите ваше имя (только буквы, пробелы и дефисы):"

def invalid_name() -> str:
    return "Имя должно содержать только буквы, пробелы и дефисы, длиной от 2 до 100 символов. Попробуйте снова:"

def ask_birthday() -> str:
    return "Введите вашу дату рождения в формате ДД.ММ или ДД-ММ (например, 15.05 или 15-05):"

def invalid_birthday() -> str:
    return "Неверный формат или некорректная дата. Пожалуйста, введите дату в формате ДД.ММ или ДД-ММ (день от 1 до 31, месяц от 1 до 12):"

def ask_brand() -> str:
    return "Выберите марку мотоцикла:"

def ask_model(brand: str) -> str:
    return f"Выберите модель {brand}:"

def ask_year() -> str:
    return "Введите год выпуска мотоцикла (от 1900 до 2025):"

def invalid_year() -> str:
    return "Год должен быть целым числом от 1900 до 2025. Попробуйте снова:"

def registration_summary(name: str, birthday: str, brand: str, model: str, year: int) -> str:
    # birthday приходит как MM-DD, преобразуем в ДД.ММ
    try:
        month, day = birthday.split('-')
        display_birthday = f"{day}.{month}"
    except:
        display_birthday = birthday
    return (
        f"📋 Проверьте введённые данные:\n"
        f"Имя: {name}\n"
        f"Дата рождения: {display_birthday}\n"
        f"Мотоцикл: {brand} {model}, {year} год\n\n"
        f"Всё верно?"
    )

def registration_success() -> str:
    return "✅ Регистрация успешно завершена! Добро пожаловать в сообщество!"

def already_registered() -> str:
    return "❌ Вы уже зарегистрированы. Повторная регистрация невозможна."

def welcome_group_message(name: str, brand: str, model: str, year: int) -> str:
    return f"🎉 Приветствуем, {name}! Рады видеть тебя в нашем мотосообществе. Мотоцикл: {brand} {model}, {year} год."

def registration_cancelled() -> str:
    return "Регистрация отменена."

def error_occurred() -> str:
    return "⚠️ Произошла ошибка. Пожалуйста, попробуйте позже."

def no_participants() -> str:
    return "Нет зарегистрированных участников."

def participants_list_header() -> str:
    return "📋 Список зарегистрированных участников:\n"

def participant_row(user) -> str:
    return f"ID: {user.telegram_id}, Имя: {user.name}, ДР: {user.birthday}, Мотоцикл: {user.bike_brand} {user.bike_model}, {user.bike_year}, Регистрация: {user.registered_at.strftime('%Y-%m-%d %H:%M')}"

def birthday_info_row(name: str, username_link: str, birthday: str, days: int) -> str:
    # birthday приходит как MM-DD, преобразуем в ДД.ММ
    try:
        month, day = birthday.split('-')
        display_birthday = f"{day}.{month}"
    except:
        display_birthday = birthday
    return f"{name} ({username_link}) — {display_birthday} — осталось {days} дн."

def no_upcoming_birthdays() -> str:
    return "В ближайшие 30 дней дней рождений нет."
