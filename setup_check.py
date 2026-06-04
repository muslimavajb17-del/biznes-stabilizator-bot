"""
Environment check script.
Run: python setup_check.py
"""
import sys
import subprocess

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

print("=" * 50)
print("  Проверка окружения — Бизнес-стабилизатор")
print("=" * 50)

# 1. Версия Python
print(f"\n✅ Python версия: {sys.version.split()[0]}")
if sys.version_info < (3, 10):
    print("❌ Нужна версия Python 3.10 или выше!")
    print("   Скачай на: https://www.python.org/downloads/")
    sys.exit(1)

# 2. Проверка зависимостей
print("\nПроверяю зависимости...")
packages = [
    ("telegram", "python-telegram-bot"),
    ("apscheduler", "APScheduler"),
    ("dotenv", "python-dotenv"),
]
all_ok = True
for module, package in packages:
    try:
        __import__(module)
        print(f"  ✅ {package}")
    except ImportError:
        print(f"  ❌ {package} — НЕ установлен")
        all_ok = False

if not all_ok:
    print("\n👉 Установи зависимости командой:")
    print("   pip install -r requirements.txt")
    sys.exit(1)

# 3. Проверка .env файла
import os
if os.path.exists(".env"):
    print("\n✅ Файл .env найден")
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("❌ BOT_TOKEN не заполнен в .env")
        print("   Получи токен у @BotFather в Telegram")
    else:
        masked = token[:10] + "..." + token[-4:]
        print(f"✅ BOT_TOKEN: {masked}")
    admin = os.getenv("ADMIN_ID", "0")
    if admin == "0":
        print("⚠️  ADMIN_ID не заполнен (можно добавить позже)")
    else:
        print(f"✅ ADMIN_ID: {admin}")
else:
    print("\n❌ Файл .env не найден")
    print("   Скопируй: cp .env.example .env")
    print("   Затем открой .env и заполни BOT_TOKEN")

print("\n" + "=" * 50)
print("  Готово к запуску? Смотри инструкцию выше.")
print("=" * 50)
