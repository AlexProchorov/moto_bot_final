# Motorcycle Community Bot

Telegram bot for motorcycle community registration and management.

## Features

- Registration via inline button in group chat
- FSM with name, birthday, motorcycle brand/model, year
- Admin commands: list participants, birthday info, upcoming birthdays
- Data stored in SQLite (or PostgreSQL)
- Configurable via .env

## Requirements

- Python 3.10+
- Dependencies: see requirements.txt

## Installation

1. Clone repository
2. Create virtual environment
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in your credentials
5. Run `python main.py`

## Configuration

Edit `.env` file:

- `BOT_TOKEN` – your bot token from @BotFather
- `ADMIN_IDS` – comma-separated Telegram user IDs of admins
- `GROUP_CHAT_ID` – ID of the group where announcements are sent
- `DATABASE_URL` – SQLAlchemy async URL (default sqlite+aiosqlite:///./bot.db)
- `MOTO_MAPPING_PATH` – path to JSON mapping file
- `LOG_LEVEL` – logging level (DEBUG, INFO, WARNING, ERROR)

## Usage

- Add bot to group and give it permission to send messages.
- Admin uses `/init` in private chat to send announcement to group.
- Users click "Пройти регистрацию" button and fill form in private chat.
- Admin uses `/participants_info`, `/bd_info`, `/bd_info_soon` in private chat to get reports.

## License

MIT