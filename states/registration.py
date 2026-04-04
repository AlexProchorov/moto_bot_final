from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_birthday = State()
    waiting_brand = State()
    waiting_model = State()
    waiting_year = State()
    confirm = State()
