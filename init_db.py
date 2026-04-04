# init_db.py
from database.engine import init_db

if __name__ == "__main__":
    init_db()
    print("✅ База данных создана")