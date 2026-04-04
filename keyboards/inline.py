from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_cancel_keyboard():
    btn = InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])

def get_cancel_back_keyboard():
    back = InlineKeyboardButton(text="🔙 Назад", callback_data="back")
    cancel = InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    return InlineKeyboardMarkup(inline_keyboard=[[back, cancel]])

def get_confirm_keyboard():
    confirm = InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm")
    change = InlineKeyboardButton(text="✏️ Изменить", callback_data="change")
    return InlineKeyboardMarkup(inline_keyboard=[[confirm, change]])

def get_brands_keyboard(mapping):
    brands = list(mapping.keys())
    keyboard = []
    row = []
    for brand in brands:
        row.append(InlineKeyboardButton(text=brand, callback_data=f"brand:{brand}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_models_keyboard(brand, models):
    keyboard = []
    row = []
    for model in models:
        row.append(InlineKeyboardButton(text=model, callback_data=f"model:{model}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
