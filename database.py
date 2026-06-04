import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id               INTEGER PRIMARY KEY,
                username              TEXT,
                first_name            TEXT,
                subscribed            INTEGER DEFAULT 1,
                day_index             INTEGER DEFAULT 0,
                joined_at             TEXT DEFAULT CURRENT_TIMESTAMP,
                last_sent             TEXT,
                onboarding_done       INTEGER DEFAULT 0,
                subscription_active   INTEGER DEFAULT 0,
                subscription_expires  TEXT,
                niche                 TEXT DEFAULT '',
                situation_category    TEXT DEFAULT ''
            )
        """)
        # Миграция: добавляем поля, если таблица уже существует
        existing = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        new_cols = {
            "onboarding_done":      "INTEGER DEFAULT 0",
            "subscription_active":  "INTEGER DEFAULT 0",
            "subscription_expires": "TEXT",
            "niche":                "TEXT DEFAULT ''",
            "situation_category":   "TEXT DEFAULT ''",
        }
        for col, definition in new_cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        conn.commit()


def add_or_update_user(user_id: int, username: str, first_name: str):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET username=?, first_name=?, subscribed=1 WHERE user_id=?",
                (username, first_name, user_id),
            )
        else:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (user_id, username, first_name),
            )
        conn.commit()


def save_onboarding(user_id: int, niche: str, situation_category: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET niche=?, situation_category=?, onboarding_done=1 WHERE user_id=?",
            (niche, situation_category, user_id),
        )
        conn.commit()


def activate_subscription(user_id: int, days: int = 30):
    expires = (datetime.now() + timedelta(days=days)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET subscription_active=1, subscription_expires=? WHERE user_id=?",
            (expires, user_id),
        )
        conn.commit()


def is_subscription_active(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT subscription_active, subscription_expires FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
    if not row or not row["subscription_active"]:
        return False
    if row["subscription_expires"]:
        expires = datetime.fromisoformat(row["subscription_expires"])
        if datetime.now() > expires:
            return False
    return True


def unsubscribe(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET subscribed=0 WHERE user_id=?", (user_id,))
        conn.commit()


def get_all_subscribed():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE subscribed=1 AND onboarding_done=1"
        ).fetchall()


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()


def increment_day(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET day_index = day_index + 1, last_sent=? WHERE user_id=?",
            (datetime.now().isoformat(), user_id),
        )
        conn.commit()


def has_lesson_sent_today(user_id: int) -> bool:
    """Защита от двойной отправки: True если урок уже был сегодня."""
    user = get_user(user_id)
    if not user or not user["last_sent"]:
        return False
    try:
        from datetime import date
        last_date = datetime.fromisoformat(user["last_sent"]).date()
        return last_date == date.today()
    except ValueError:
        return False


def get_stats():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM users WHERE subscribed=1").fetchone()[0]
        paid = conn.execute(
            "SELECT COUNT(*) FROM users WHERE subscription_active=1"
        ).fetchone()[0]
        return total, active, paid
